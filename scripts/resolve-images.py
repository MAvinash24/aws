"""Resolve official Docker Hub tags to Linux amd64 digests; no Docker required."""
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPT = ", ".join(["application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json", "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"])


def resolve(repository, tag):
    query = urllib.parse.urlencode({"service": "registry.docker.io", "scope": "repository:" + repository + ":pull"})
    with urllib.request.urlopen("https://auth.docker.io/token?" + query, timeout=30) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request("https://registry-1.docker.io/v2/" + repository + "/manifests/" + tag, headers={"Authorization": "Bearer " + token, "Accept": ACCEPT})
    with urllib.request.urlopen(request, timeout=30) as response:
        digest = response.headers["Docker-Content-Digest"]
        manifest = json.load(response)
    for item in manifest.get("manifests", []):
        platform = item.get("platform", {})
        if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
            digest = item["digest"]
            break
    else:
        if manifest.get("manifests"):
            raise ValueError("No Linux amd64 image")
    return repository + "@" + digest


def main():
    pins = {"python": {"tag": "3.12-alpine3.23", "image": resolve("library/python", "3.12-alpine3.23")},
            "falco": {"tag": "0.45.0", "image": resolve("falcosecurity/falco", "0.45.0")},
            "registry_test": {"tag": "3", "image": resolve("library/registry", "3")}}
    (ROOT / "security/images.lock.json").write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    dockerfile = ROOT / "Dockerfile"
    lines = dockerfile.read_text().splitlines()
    lines[0] = "FROM " + pins["python"]["image"]
    dockerfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Pinned official Linux amd64 images. Verify the Falco signature before provisioning.")


if __name__ == "__main__":
    main()
