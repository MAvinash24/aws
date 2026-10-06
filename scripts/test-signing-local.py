"""Real Cosign OCI signing tests against a disposable localhost-only registry.

This does not use AWS credentials or production signing keys.
"""
import argparse
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--cosign", default="cosign")
    parser.add_argument("--port", default=15000, type=int)
    args = parser.parse_args()
    lock = json.loads((ROOT / "security/images.lock.json").read_text())
    registry = "localhost:" + str(args.port)
    image = registry + "/devsecops-test:integration"
    run = lambda command, **kw: subprocess.run(command, check=True, timeout=300, **kw)
    container = None
    try:
        container = run([args.docker, "run", "--detach", "--publish", f"127.0.0.1:{args.port}:5000", lock["registry_test"]["image"]], capture_output=True, text=True).stdout.strip()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://{registry}/v2/", timeout=2):
                    break
            except (OSError, urllib.error.URLError):
                time.sleep(1)
        else:
            raise RuntimeError("Local registry did not become ready")
        run([args.docker, "tag", "devsecops-app:local", image])
        run([args.docker, "push", image], stdout=subprocess.DEVNULL)
        inspect = json.loads(run([args.docker, "image", "inspect", image], capture_output=True, text=True).stdout)[0]
        digest = next(value for value in inspect["RepoDigests"] if value.startswith(registry + "/devsecops-test@"))
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, COSIGN_PASSWORD=secrets.token_urlsafe(32), DOCKER_CONFIG=directory, COSIGN_EXPERIMENTAL="1")
            key = str(Path(directory) / "trusted")
            wrong = str(Path(directory) / "wrong")
            for prefix in (key, wrong):
                run([args.cosign, "generate-key-pair", "--output-key-prefix", prefix], env=env, stdout=subprocess.DEVNULL)
            common = ["--allow-insecure-registry"]
            verify = [args.cosign, "verify", "--key", key + ".pub", "--insecure-ignore-tlog=true", *common, digest]
            unsigned = subprocess.run(verify, env=env, capture_output=True, timeout=120)
            if unsigned.returncode == 0:
                raise RuntimeError("Unsigned image unexpectedly accepted")
            run([args.cosign, "sign", "--yes", "--key", key + ".key", "--signing-config", str(ROOT / "security/cosign-signing.json"), "--registry-referrers-mode=oci-1-1", *common, digest], env=env, stdout=subprocess.DEVNULL)
            run(verify, env=env, stdout=subprocess.DEVNULL)
            wrong_key = [args.cosign, "verify", "--key", wrong + ".pub", "--insecure-ignore-tlog=true", *common, digest]
            rejected = subprocess.run(wrong_key, env=env, capture_output=True, timeout=120)
            if rejected.returncode == 0:
                raise RuntimeError("Wrong trusted key unexpectedly accepted")
            result = {"signedDigest": digest, "unsignedRejected": True, "correctKeyAccepted": True, "wrongKeyRejected": True, "registry": "disposable localhost OCI 1.1; not ECR"}
            (ROOT / "reports").mkdir(exist_ok=True)
            (ROOT / "reports/signing-local.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print("Signing integration: unsigned rejected; valid key accepted; wrong key rejected")
    finally:
        if container:
            subprocess.run([args.docker, "rm", "--force", container], check=False, capture_output=True, timeout=30)


if __name__ == "__main__":
    main()
