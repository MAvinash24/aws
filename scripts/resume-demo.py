"""Resume only the configured demo host and pipeline; deployment still verifies."""
import argparse
import importlib.util
from pathlib import Path


def main():
    import boto3
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("deploy.local.json"))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("provision", Path(__file__).with_name("provision.py"))
    provision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provision)
    config = provision.config_values(args.config)
    session = boto3.Session(region_name=config["region"])
    if session.client("sts").get_caller_identity()["Account"] != config["expected_account"]:
        raise SystemExit("Wrong AWS account")
    project = config["project"]
    if config.get("ci_provider") == "github":
        from github_api import request
        # Verify GitHub access before changing AWS compute.
        request(config["github_repository"], "workflows/deploy.yml")
    outputs = provision.stack_outputs(session.client("cloudformation"), project + "-runtime")
    session.client("autoscaling").update_auto_scaling_group(AutoScalingGroupName=outputs["AutoScalingGroup"], MinSize=1, MaxSize=1, DesiredCapacity=1)
    if config.get("ci_provider") == "github":
        request(config["github_repository"], "workflows/deploy.yml/enable", "PUT")
        request(config["github_repository"], "workflows/deploy.yml/dispatches", "POST", {"ref": config["github_branch"]})
        print("Host resumed; GitHub Actions verification and deployment requested")
        return
    pipeline = session.client("codepipeline")
    pipeline.enable_stage_transition(pipelineName=project, stageName="BuildScanSign", transitionType="Inbound")
    execution = pipeline.start_pipeline_execution(name=project)
    print("Host and pipeline resumed:", execution["pipelineExecutionId"])


if __name__ == "__main__":
    main()
