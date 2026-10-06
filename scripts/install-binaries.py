"""Download only pinned official assets, verify SHA-256 before extraction."""
import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install(name, spec, destination):
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "devsecops-demo-installer"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError("Checksum mismatch for " + name)
    expected = name + (".exe" if os.name == "nt" else "")
    if spec["filename"].endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            entries = [entry for entry in archive.getmembers() if entry.isfile() and Path(entry.name).name == expected]
            if len(entries) != 1:
                raise ValueError("Expected exactly one binary in " + name)
            data = archive.extractfile(entries[0]).read()
    elif spec["filename"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = [entry for entry in archive.namelist() if Path(entry).name == expected]
            if len(entries) != 1:
                raise ValueError("Expected exactly one binary in " + name)
            data = archive.read(entries[0])
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination, delete=False) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.chmod(0o755)
        temporary_path.replace(destination / expected)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(name + " " + spec["version"] + ": verified and installed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["cosign", "trivy", "cfn-guard"])
    parser.add_argument("--output", type=Path, default=ROOT / ".tools")
    args = parser.parse_args()
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("These pinned assets require x86-64.")
    system = "windows" if os.name == "nt" else "linux"
    if system == "linux" and platform.system() != "Linux":
        raise SystemExit("Use Linux/WSL or Windows; macOS assets are not configured.")
    lock = json.loads((ROOT / "security/tools.lock.json").read_text(encoding="utf-8-sig"))
    for name, specs in lock.items():
        if not args.only or args.only == name:
            install(name, specs[system], args.output)


if __name__ == "__main__":
    main()
