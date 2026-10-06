import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("deploy", Path(__file__).resolve().parents[1] / "scripts/deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
REPO = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/devsecops-demo"
IMAGE = REPO + "@sha256:" + "a" * 64


class DeploymentTests(unittest.TestCase):
    def test_only_expected_repository_and_digest(self):
        self.assertEqual(deploy.validate_release({"image": IMAGE, "source": "f" * 40}, REPO), IMAGE)
        for bad in (REPO + ":latest", IMAGE.replace("devsecops-demo", "attacker"), IMAGE[:-1], IMAGE + ";echo attack"):
            with self.subTest(image=bad), self.assertRaises(ValueError):
                deploy.validate_release({"image": bad, "source": "f" * 40}, REPO)

    def test_invalid_commit(self):
        with self.assertRaises(ValueError):
            deploy.validate_release({"image": IMAGE, "source": "main"}, REPO)

    def test_invalid_signature_never_updates_ecs(self):
        ecs = Mock()
        rejected = Mock(side_effect=RuntimeError("signature rejected"))
        with self.assertRaises(RuntimeError):
            deploy.verify_and_update(ecs, "demo", "demo", {}, IMAGE, rejected)
        ecs.register_task_definition.assert_not_called()
        ecs.update_service.assert_not_called()

    def test_exact_digest_deployed_after_verification(self):
        ecs = Mock()
        ecs.register_task_definition.return_value = {"taskDefinition": {"taskDefinitionArn": "verified-revision"}}
        ecs.describe_services.return_value = {"services": [{"taskDefinition": "verified-revision", "runningCount": 1, "pendingCount": 0}]}
        task = {"family": "demo", "containerDefinitions": [{"name": "app", "image": "old"}]}
        def verified(image):
            self.assertEqual(image, IMAGE)
            ecs.register_task_definition.assert_not_called()
        deploy.verify_and_update(ecs, "demo", "demo", task, IMAGE, verified)
        self.assertEqual(ecs.register_task_definition.call_args.kwargs["containerDefinitions"][0]["image"], IMAGE)
        self.assertEqual(ecs.update_service.call_args.kwargs["taskDefinition"], "verified-revision")

    def test_rollback_is_not_reported_as_success(self):
        ecs = Mock()
        ecs.register_task_definition.return_value = {"taskDefinition": {"taskDefinitionArn": "new-revision"}}
        ecs.describe_services.return_value = {"services": [{"taskDefinition": "old-revision", "runningCount": 1, "pendingCount": 0}]}
        with self.assertRaises(RuntimeError):
            deploy.verify_and_update(ecs, "demo", "demo", {"containerDefinitions": [{}]}, IMAGE, lambda _: None)

    def test_hardening_rejects_privileged_or_host_mount(self):
        task = {"family": "demo", "networkMode": "bridge", "executionRoleArn": "execution", "taskRoleArn": "task", "containerDefinitions": [{"name": "app", "user": "10001:10001", "readonlyRootFilesystem": True, "linuxParameters": {"capabilities": {"drop": ["ALL"]}}}]}
        deploy.validate_task(task, "demo", "execution", "task")
        task["containerDefinitions"][0]["privileged"] = True
        with self.assertRaises(ValueError):
            deploy.validate_task(task, "demo", "execution", "task")
        task["containerDefinitions"][0]["privileged"] = False
        task["volumes"] = [{"host": {"sourcePath": "/"}}]
        with self.assertRaises(ValueError):
            deploy.validate_task(task, "demo", "execution", "task")
