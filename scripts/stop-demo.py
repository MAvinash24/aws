"""Stop project compute without deleting evidence; explicitly restart before reuse."""
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
    pipeline = session.client("codepipeline")
    pipeline.disable_stage_transition(pipelineName=project, stageName="BuildScanSign", transitionType="Inbound", reason="Demo compute stopped to limit charges")
    running = []
    for page in pipeline.get_paginator("list_pipeline_executions").paginate(pipelineName=project):
        running.extend(item["pipelineExecutionId"] for item in page["pipelineExecutionSummaries"] if item["status"] in ("InProgress", "Stopping"))
    for execution in running:
        status = pipeline.get_pipeline_execution(pipelineName=project, pipelineExecutionId=execution)["pipelineExecution"]["status"]
        if status == "InProgress":
            pipeline.stop_pipeline_execution(pipelineName=project, pipelineExecutionId=execution, abandon=False, reason="Stop demo compute")
    # Finish active actions before scaling down, preventing a concurrent deploy
    # from restoring DesiredCount=1 after shutdown.
    import time
    deadline = time.monotonic() + 2100
    while running and time.monotonic() < deadline:
        running = [execution for execution in running if pipeline.get_pipeline_execution(pipelineName=project, pipelineExecutionId=execution)["pipelineExecution"]["status"] in ("InProgress", "Stopping")]
        if running:
            time.sleep(10)
    if running:
        raise SystemExit("Pipeline actions have not stopped. No compute was scaled down; inspect the execution and retry.")
    ecs = session.client("ecs")
    ecs.update_service(cluster=project, service=project, desiredCount=0)
    ecs.get_waiter("services_stable").wait(cluster=project, services=[project])
    outputs = provision.stack_outputs(session.client("cloudformation"), project + "-runtime")
    session.client("autoscaling").update_auto_scaling_group(AutoScalingGroupName=outputs["AutoScalingGroup"], MinSize=0, DesiredCapacity=0)
    print("App and host stopped. ECR, S3, logs, signatures and keys remain; stored data can still incur charges.")


if __name__ == "__main__":
    main()
