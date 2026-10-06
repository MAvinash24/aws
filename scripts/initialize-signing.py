"""Create a private signing key once; store it as standard SecureString in SSM."""
import argparse
import getpass
import os
import subprocess
import tempfile
from pathlib import Path


def main():
    import boto3
    from botocore.exceptions import ClientError
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("deploy.local.json"))
    args = parser.parse_args()
    import importlib.util
    spec = importlib.util.spec_from_file_location("provision", Path(__file__).with_name("provision.py"))
    provision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provision)
    config = provision.config_values(args.config)
    session = boto3.Session(region_name=config["region"])
    if session.client("sts").get_caller_identity()["Account"] != config["expected_account"]:
        raise SystemExit("Wrong AWS account")
    ssm = session.client("ssm")
    prefix = "/" + config["project"] + "/signing/"
    for suffix in ("private-key", "password", "public-key"):
        try:
            ssm.get_parameter(Name=prefix + suffix)
        except ClientError as error:
            if error.response["Error"]["Code"] != "ParameterNotFound":
                raise
        else:
            raise SystemExit("Signing parameter already exists; refusing to overwrite trust material")
    password = getpass.getpass("New signing-key passphrase (not your AWS password): ")
    if len(password) < 16 or password != getpass.getpass("Confirm passphrase: "):
        raise SystemExit("Use matching passphrases with at least 16 characters")
    with tempfile.TemporaryDirectory() as folder:
        subprocess.run(["cosign", "generate-key-pair"], cwd=folder, env=dict(os.environ, COSIGN_PASSWORD=password), check=True)
        values = [("private-key", (Path(folder) / "cosign.key").read_text(), "SecureString"),
                  ("password", password, "SecureString"), ("public-key", (Path(folder) / "cosign.pub").read_text(), "String")]
        for suffix, value, kind in values:
            ssm.put_parameter(Name=prefix + suffix, Value=value, Type=kind, Tier="Standard", Overwrite=False, Tags=[{"Key": "Project", "Value": config["project"]}])
    print("Signing parameters created. No private key was written into the repository.")


if __name__ == "__main__":
    main()
