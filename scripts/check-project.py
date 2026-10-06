"""Portable local checks for generated IaC and permission separation."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location("generate", ROOT / "infra/generate.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    for name in ("platform", "runtime", "pipeline", "github"):
        actual = json.loads((ROOT / f"infra/{name}.json").read_text())
        if actual != getattr(generator, "generate_" + name)():
            raise SystemExit("Generated infrastructure is stale: run python infra/generate.py")
        for logical_id, item in actual["Resources"].items():
            props = item["Properties"]
            if item["Type"] == "AWS::IAM::Role":
                if not props.get("PermissionsBoundary"):
                    raise SystemExit("Missing boundary: " + logical_id)
                for policy in props.get("Policies", []):
                    for stmt in policy["PolicyDocument"]["Statement"]:
                        if "*" in stmt["Action"]:
                            raise SystemExit("Wildcard IAM action: " + logical_id)
    pipeline = generator.generate_pipeline()["Resources"]
    build = json.dumps(pipeline["BuildRole"])
    deploy = json.dumps(pipeline["DeployRole"])
    if "ecs:UpdateService" in build or "ecs:RegisterTaskDefinition" in build or "iam:PassRole" in build:
        raise SystemExit("Build role has deployment permissions")
    if "private-key" in deploy or "signing/password" in deploy or "ecr:PutImage" in deploy:
        raise SystemExit("Deploy role has signing or push permissions")
    github = generator.generate_github()["Resources"]
    build = json.dumps(github["GithubBuildRole"])
    deploy = json.dumps(github["GithubDeployRole"])
    if any(action in build for action in ("ecs:UpdateService", "ecs:RegisterTaskDefinition", "iam:PassRole")):
        raise SystemExit("GitHub build role can deploy")
    if any(value in deploy for value in ("private-key", "signing/password", "ecr:PutImage")):
        raise SystemExit("GitHub deploy role can sign or push")
    print("Project consistency and permission separation: PASS")


if __name__ == "__main__":
    main()
