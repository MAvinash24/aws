"""Preview or explicitly execute one project stack. Does not modify other stacks."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def config_values(path):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,23}", config.get("project", "")):
        raise ValueError("Invalid project name")
    if not re.fullmatch(r"[0-9]{12}", config.get("expected_account", "")):
        raise ValueError("Set expected_account to your 12-digit account ID")
    return config


def stack_outputs(cf, name):
    stacks = cf.describe_stacks(StackName=name)["Stacks"]
    if not stacks[0]["StackStatus"].endswith("_COMPLETE") or "ROLLBACK" in stacks[0]["StackStatus"]:
        raise ValueError("Dependency stack is not healthy: " + name)
    return {item["OutputKey"]: item["OutputValue"] for item in stacks[0].get("Outputs", [])}


def build_parameters(stage, config, outputs):
    result = {"ProjectName": config["project"]}
    if stage == "runtime":
        for key in ("HostProfileArn", "ExecutionRoleArn", "TaskRoleArn"):
            result[key] = outputs[key]
        result.update({"VpcId": config["vpc_id"], "SubnetId": config["subnet_id"], "InstanceType": config["instance_type"], "InitialImage": outputs["RepositoryUri"] + ":not-deployed"})
        pins = json.loads((ROOT / "security/images.lock.json").read_text())
        result["FalcoImage"] = pins["falco"]["image"]
    elif stage == "pipeline":
        for key in ("ArtifactBucket", "RepositoryUri", "RepositoryArn", "BoundaryArn", "ExecutionRoleArn", "TaskRoleArn"):
            result[key] = outputs[key]
        result.update({"ConnectionArn": config["connection_arn"], "FullRepositoryId": config["github_repository"], "BranchName": config["github_branch"]})
    return [{"ParameterKey": key, "ParameterValue": value} for key, value in result.items()]


def check_network(session, config):
    ec2 = session.client("ec2")
    subnet = ec2.describe_subnets(SubnetIds=[config["subnet_id"]])["Subnets"][0]
    if subnet["VpcId"] != config["vpc_id"]:
        raise ValueError("Subnet does not belong to the selected VPC")
    tables = ec2.describe_route_tables(Filters=[{"Name": "association.subnet-id", "Values": [config["subnet_id"]]}])["RouteTables"]
    if not tables:
        tables = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [config["vpc_id"]]}, {"Name": "association.main", "Values": ["true"]}])["RouteTables"]
    if not any(route.get("DestinationCidrBlock") == "0.0.0.0/0" and route.get("GatewayId", "").startswith("igw-") and route.get("State") == "active" for table in tables for route in table["Routes"]):
        raise ValueError("Selected subnet needs an active Internet Gateway route; no NAT is created")


def main():
    import boto3
    from botocore.exceptions import ClientError
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["platform", "runtime", "pipeline"])
    parser.add_argument("--config", type=Path, default=ROOT / "deploy.local.json")
    parser.add_argument("--execute", action="store_true", help="Execute the reviewed CloudFormation change set; creates billable resources")
    args = parser.parse_args()
    config = config_values(args.config)
    session = boto3.Session(region_name=config["region"])
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != config["expected_account"]:
        raise SystemExit("Wrong AWS account. No change was made.")
    cf = session.client("cloudformation")
    project = config["project"]
    if args.stage == "platform":
        scan = session.client("ecr").get_registry_scanning_configuration()["scanningConfiguration"]
        if scan["scanType"] != "BASIC":
            raise SystemExit("Registry currently uses ENHANCED scanning. Review switching to BASIC in ECR Console before this project; no account-wide settings were changed.")
    name = project + "-" + args.stage
    outputs = {} if args.stage == "platform" else stack_outputs(cf, project + "-platform")
    if args.stage == "runtime":
        check_network(session, config)
    if args.stage == "pipeline":
        stack_outputs(cf, project + "-runtime")
        connection = session.client("codeconnections").get_connection(ConnectionArn=config["connection_arn"])["Connection"]
        if connection["ConnectionStatus"] != "AVAILABLE":
            raise SystemExit("GitHub connection is not AVAILABLE. Complete authorization in AWS Console.")
        ssm = session.client("ssm")
        # Metadata only; do not expose key or password to this preflight.
        expected = {f"/{project}/signing/{part}" for part in ("private-key", "password", "public-key")}
        found = set()
        for page in ssm.get_paginator("describe_parameters").paginate(ParameterFilters=[{"Key": "Name", "Option": "BeginsWith", "Values": [f"/{project}/signing/"]}]):
            found.update(item["Name"] for item in page["Parameters"])
        if not expected.issubset(found):
            raise SystemExit("Initialize signing keys before the pipeline starts")
    template = (ROOT / f"infra/{args.stage}.json").read_text()
    parameters = build_parameters(args.stage, config, outputs)
    kind = "CREATE"
    try:
        existing = cf.describe_stacks(StackName=name)["Stacks"][0]
        # Runtime update after pipeline deployment could revert the running revision.
        if args.stage == "runtime":
            raise SystemExit("Runtime stack already exists. Review a separate change set before updating it; preserve the deployed task revision and DesiredCount.")
        if existing.get("StackStatus") == "REVIEW_IN_PROGRESS":
            kind = "CREATE"
        elif existing.get("Tags") != [{"Key": "Project", "Value": project}]:
            raise SystemExit("Existing stack lacks the exact project ownership tag. No change made.")
        else:
            kind = "UPDATE"
    except ClientError as error:
        if error.response["Error"]["Code"] != "ValidationError" or "does not exist" not in error.response["Error"]["Message"]:
            raise
    change = cf.create_change_set(StackName=name, ChangeSetName="review-" + str(int(time.time())), ChangeSetType=kind, TemplateBody=template,
                                Parameters=parameters, Capabilities=["CAPABILITY_NAMED_IAM"], Tags=[{"Key": "Project", "Value": project}])
    cf.get_waiter("change_set_create_complete").wait(ChangeSetName=change["Id"], WaiterConfig={"Delay": 5, "MaxAttempts": 120})
    plan = cf.describe_change_set(ChangeSetName=change["Id"])
    Path("reports").mkdir(exist_ok=True)
    path = Path("reports") / ("changeset-" + args.stage + ".json")
    path.write_text(json.dumps({"account": identity["Account"], "region": config["region"], "templateSha256": hashlib.sha256(template.encode()).hexdigest(), "changeset": plan}, indent=2, default=str), encoding="utf-8")
    print("Change set prepared:", name, "in", config["region"])
    print("Review:", path)
    if not args.execute:
        print("No resources executed. Re-run with --execute only after reviewing the configuration.")
        return
    cf.execute_change_set(ChangeSetName=change["Id"])
    waiter = "stack_create_complete" if kind == "CREATE" else "stack_update_complete"
    cf.get_waiter(waiter).wait(StackName=name, WaiterConfig={"Delay": 15, "MaxAttempts": 120})
    print("Stack completed:", name)
    print(json.dumps(stack_outputs(cf, name), indent=2))


if __name__ == "__main__":
    main()
