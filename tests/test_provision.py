import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("provision", Path(__file__).resolve().parents[1] / "scripts/provision.py")
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


class ProvisionTests(unittest.TestCase):
    def test_account_must_be_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text(json.dumps({"project": "demo", "expected_account": "REPLACE"}))
            with self.assertRaises(ValueError):
                provision.config_values(config)

    def test_invalid_project_name_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text(json.dumps({"project": "../../other-account", "expected_account": "123456789012"}))
            with self.assertRaises(ValueError):
                provision.config_values(config)

    def test_runtime_uses_pinned_sensor_and_zero_bootstrap_image(self):
        config = {"project": "demo", "vpc_id": "vpc-1", "subnet_id": "subnet-1", "instance_type": "t3.micro"}
        outputs = {"HostProfileArn": "host", "ExecutionRoleArn": "execution", "TaskRoleArn": "task", "RepositoryUri": "repo"}
        result = {item["ParameterKey"]: item["ParameterValue"] for item in provision.build_parameters("runtime", config, outputs)}
        self.assertIn("@sha256:", result["FalcoImage"])
        self.assertEqual(result["InitialImage"], "repo:not-deployed")
