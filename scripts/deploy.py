"""Verify trusted signature BEFORE registering or updating anything in ECS."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def validate_release(release, expected_repository):
    image = release.get("image", "")
    if not isinstance(image, str) or not re.fullmatch(re.escape(expected_repository) + r"@sha256:[a-f0-9]{64}", image):
        raise ValueError("Release must name a digest in the configured ECR repository")
    source = release.get("source", "")
    if not isinstance(source, str) or not re.fullmatch(r"[a-f0-9]{40}", source):
        raise ValueError("Release must identify the full Git commit")
    return image


def validate_task(task, project, execution_role, task_role):
    if task.get("family") != project or task.get("networkMode") != "bridge":
        raise ValueError("Unexpected task family or network mode")
    if task.get("executionRoleArn") != execution_role or task.get("taskRoleArn") != task_role:
        raise ValueError("Unexpected task role")
    if task.get("volumes") or task.get("pidMode") or task.get("ipcMode"):
        raise ValueError("Host volumes and namespaces are prohibited")
    containers = task.get("containerDefinitions", [])
    if len(containers) != 1 or containers[0].get("name") != "app":
        raise ValueError("Unexpected containers")
    app = containers[0]
    if app.get("privileged", False) or app.get("user") != "10001:10001" or not app.get("readonlyRootFilesystem"):
        raise ValueError("Application must be unprivileged, non-root, and read-only")
    linux = app.get("linuxParameters", {})
    caps = linux.get("capabilities", {})
    if "ALL" not in caps.get("drop", []) or caps.get("add") or linux.get("devices"):
        raise ValueError("Unexpected Linux capabilities/devices")
    if app.get("mountPoints") or app.get("volumesFrom"):
        raise ValueError("Application host mounts are prohibited")
    return app


def verify_and_update(ecs, cluster, service, task, image, verify):
    # Invariant tested with rejected signatures: no AWS mutation before success.
    verify(image)
    allowed = {key: task[key] for key in ("family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions", "volumes", "placementConstraints", "requiresCompatibilities", "cpu", "memory") if key in task}
    allowed["containerDefinitions"][0]["image"] = image
    registered = ecs.register_task_definition(**allowed)["taskDefinition"]["taskDefinitionArn"]
    ecs.update_service(cluster=cluster, service=service, taskDefinition=registered, desiredCount=1)
    ecs.get_waiter("services_stable").wait(cluster=cluster, services=[service], WaiterConfig={"Delay": 15, "MaxAttempts": 80})
    active = ecs.describe_services(cluster=cluster, services=[service])["services"][0]
    if active["taskDefinition"] != registered or active["runningCount"] != 1 or active["pendingCount"] != 0:
        raise RuntimeError("Service rolled back or did not reach the verified task revision")
    return registered


def main():
    import boto3
    project = os.environ["PROJECT_NAME"]
    release_path = Path(os.environ.get("RELEASE_DIR") or os.environ["CODEBUILD_SRC_DIR_Release"]) / "release.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    image = validate_release(release, os.environ["ECR_URI"])
    source = os.environ.get("RELEASE_SOURCE") or os.environ["CODEBUILD_RESOLVED_SOURCE_VERSION"]
    if release["source"] != source:
        raise ValueError("Build artifact and deploy source commit do not match")
    ssm, ecs = boto3.client("ssm"), boto3.client("ecs")
    key = ssm.get_parameter(Name=f"/{project}/signing/public-key")["Parameter"]["Value"]
    service = ecs.describe_services(cluster=project, services=[project])
    if service.get("failures") or len(service.get("services", [])) != 1:
        raise ValueError("ECS service not found")
    task = ecs.describe_task_definition(taskDefinition=service["services"][0]["taskDefinition"])["taskDefinition"]
    validate_task(task, project, os.environ["EXECUTION_ROLE_ARN"], os.environ["TASK_ROLE_ARN"])
    ecr = boto3.client("ecr")
    import base64
    auth = ecr.get_authorization_token()["authorizationData"][0]
    username, password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    with tempfile.TemporaryDirectory() as directory:
        public = Path(directory) / "cosign.pub"
        public.write_text(key, encoding="utf-8")
        env = dict(os.environ, DOCKER_CONFIG=directory, COSIGN_EXPERIMENTAL="1")
        # Credential only in temporary Docker config, never command arguments/logs.
        registry = os.environ["ECR_URI"].split("/")[0]
        config = {"auths": {registry: {"auth": base64.b64encode((username + ":" + password).encode()).decode()}}}
        (Path(directory) / "config.json").write_text(json.dumps(config), encoding="utf-8")

        def verify(digest):
            subprocess.run(["cosign", "verify", "--key", str(public), "--insecure-ignore-tlog=true", digest], env=env, check=True, timeout=180, stdout=subprocess.DEVNULL)

        registered = verify_and_update(ecs, project, project, task, image, verify)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/deployment.json").write_text(json.dumps({"image": image, "source": release["source"], "taskDefinition": registered, "verified": True}, indent=2), encoding="utf-8")
    print("Verified image deployed and service is stable:", image)


if __name__ == "__main__":
    main()
