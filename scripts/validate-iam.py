"""Validate actual deployed role policies and boundary with Access Analyzer."""
import json
import os
from pathlib import Path


def main():
    import boto3
    iam, analyzer = boto3.client("iam"), boto3.client("accessanalyzer")
    project = os.environ["PROJECT_NAME"]
    policies = []
    for suffix in ("host", "task", "execution", "build", "deploy", "pipeline"):
        name = project + "-" + suffix
        pages = iam.get_paginator("list_role_policies").paginate(RoleName=name)
        for page in pages:
            for policy_name in page["PolicyNames"]:
                policies.append((name + "/" + policy_name, iam.get_role_policy(RoleName=name, PolicyName=policy_name)["PolicyDocument"]))
    arn = os.environ["BOUNDARY_ARN"]
    version = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
    policies.append(("boundary", iam.get_policy_version(PolicyArn=arn, VersionId=version)["PolicyVersion"]["Document"]))
    reports, blocked = [], False
    for name, policy in policies:
        findings = []
        for page in analyzer.get_paginator("validate_policy").paginate(policyDocument=json.dumps(policy), policyType="IDENTITY_POLICY"):
            findings.extend(page["findings"])
        reports.append({"name": name, "findings": findings})
        if any(f["findingType"] in ("ERROR", "SECURITY_WARNING") for f in findings):
            blocked = True
    Path("reports").mkdir(exist_ok=True)
    Path("reports/iam-validation.json").write_text(json.dumps(reports, indent=2, default=str), encoding="utf-8")
    if blocked:
        raise SystemExit("Access Analyzer rejected an IAM policy. Inspect reports/iam-validation.json")
    print("IAM validation: no errors or security warnings")


if __name__ == "__main__":
    main()
