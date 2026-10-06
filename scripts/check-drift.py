"""Explicit on-demand drift check, no AWS Config recorder."""
import argparse
import json
import time
from pathlib import Path


def main():
    import boto3
    parser = argparse.ArgumentParser()
    parser.add_argument("stack")
    args = parser.parse_args()
    client = boto3.client("cloudformation")
    detection = client.detect_stack_drift(StackName=args.stack)["StackDriftDetectionId"]
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        status = client.describe_stack_drift_detection_status(StackDriftDetectionId=detection)
        if status["DetectionStatus"] == "DETECTION_FAILED":
            raise SystemExit(status.get("DetectionStatusReason", "Drift detection failed"))
        if status["DetectionStatus"] == "DETECTION_COMPLETE":
            break
        time.sleep(10)
    else:
        raise SystemExit("Drift detection timed out")
    results = []
    for page in client.get_paginator("describe_stack_resource_drifts").paginate(StackName=args.stack):
        results.extend(page["StackResourceDrifts"])
    Path("reports").mkdir(exist_ok=True)
    Path("reports/drift.json").write_text(json.dumps({"status": status, "resources": results}, indent=2, default=str), encoding="utf-8")
    print("Stack drift:", status["StackDriftStatus"])
    if status["StackDriftStatus"] != "IN_SYNC":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
