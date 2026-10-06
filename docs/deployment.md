# Deployment guide: Mumbai, single-account demo

## 1. Finish AWS verification and prepare the repository

AWS currently blocks CloudShell with “Your account verification is in progress”. Complete any verification steps shown by AWS. Do not create another account, switch billing plans, join an Organization, or enable paid trials to bypass it.

Upload this source to `https://github.com/MAvinash24/aws` on `main`. Exclude `.venv`, `.tools`, `.secrets`, `reports`, `dist`, signing keys and local account configuration. The original assignment screenshots are reference material; they are not needed in the source repository. A private repository limits unnecessary exposure of project material.

Protect the release branch against unauthorized changes to buildspecs, signing code, IAM and deployment verification. GitHub Free private repositories may limit branch-protection features; where unavailable, restrict collaborators and manually review all changes before pushing. Local pre-commit hooks are convenience checks and can be bypassed. The AWS pipeline is the actual gate.

## 2. Console checks (no resource creation)

In Mumbai, inspect Billing/Free Tier/Credits and establish the spending limit you are prepared to accept. Check EC2 instance eligibility **for your account**, EBS, IPv4, CodeBuild/CodePipeline minute allowances, ECR storage and log use. Credits are time-limited; this is a small-cost architecture, not a permanent free-service guarantee.

In VPC, select an existing VPC and subnet with an active Internet Gateway route. No inbound ports are required. The EC2 host uses a public IPv4 for outbound registry/API traffic. No SSH key, NAT gateway or load balancer is needed.

In ECR → Private registry → Scanning, confirm **BASIC** scanning. The provisioning script refuses to alter an account currently using ENHANCED scanning. Existing registry filters may override repository scan-on-push behavior: review that the project's repository is covered by a SCAN_ON_PUSH rule. BASIC scanning is supplementary; Trivy is the deployment-blocking CVE gate.

In Developer Tools → Settings → Connections, create a **GitHub** connection in Mumbai and complete GitHub authorization for `MAvinash24/aws`. It must show **Available**, not Pending. Copy the `arn:aws:codeconnections:...` connection ARN. Authorize access only to the intended repository. This connection authorization grants AWS access to the repository and must be reviewed by the account owner.

## 3. Upload the project into CloudShell

After verification completes, open CloudShell in Mumbai. Use Actions → Upload file to upload the prepared source ZIP. Unzip it into a project directory. Start a shell from the project root.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-tools.txt
python scripts/install-binaries.py --output .tools
export PATH="$PWD/.tools:$PATH"
cp deploy.example.json deploy.local.json
```

Edit `deploy.local.json`: enter your 12-digit account ID, VPC/subnet IDs and AVAILABLE connection ARN. Repository is already `MAvinash24/aws`, branch `main`, region `ap-south-1`. Keep it out of Git. Run `aws sts get-caller-identity` and compare the account to your configuration. Prefer a scoped administrative setup identity over using the root account.

The scripts use current session credentials. They do not request long-lived access keys. Boto3 is included in the tools requirements. AWS CLI is already installed in CloudShell.

## 4. Platform stack

```bash
python scripts/provision.py platform
```

This creates a reviewable CloudFormation **change set**, without executing it. Inspect `reports/changeset-platform.json` and the CloudFormation Console. It includes a private ECR repository, retained encrypted artifact bucket, logs, IAM permissions boundary, task/execution/host roles, and alerting.

When the account owner has reviewed the resource costs and IAM permissions:

```bash
python scripts/provision.py platform --execute
```

Execution creates the named resources. The templates are available for Console deployment instead: upload `infra/platform.json`, set `ProjectName`, review the change set and acknowledge creation of named IAM roles. Do not grant AdministratorAccess to pipeline roles.

## 5. Signing trust

With `.tools` on PATH:

```bash
python scripts/initialize-signing.py
```

Enter a new passphrase directly into the terminal prompt, at least 16 characters. It is **not** your AWS password. The script generates a Cosign key pair in temporary storage and creates three standard SSM parameters:

| Parameter | Type | Reader |
|---|---|---|
| `/devsecops-demo/signing/private-key` | SecureString | Build role |
| `/devsecops-demo/signing/password` | SecureString | Build role |
| `/devsecops-demo/signing/public-key` | String | Deploy role |

SecureStrings use the AWS-managed SSM encryption key. No customer-managed KMS key or Secrets Manager secret is created. The script refuses to overwrite existing trust material. If an upload fails partway, inspect the three parameters before retrying; do not blindly rotate or overwrite them. An account administrator can still read/change them. Keep SSM write privileges away from developers and runtime roles.

## 6. Runtime stack

Falco's version and Linux amd64 digest are in `security/images.lock.json`. Verify its publisher signature against the pinned release tag before provisioning:

```bash
cosign verify docker.io/falcosecurity/falco:0.45.0 \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  --certificate-identity-regexp=https://github.com/falcosecurity/falco/ \
  --certificate-github-workflow-ref=refs/tags/0.45.0
python scripts/provision.py runtime
python scripts/provision.py runtime --execute
```

This creates one EC2 host, with IMDSv2, an encrypted 30-GiB gp3 volume, no ingress and standard CPU credits. ECS starts with **zero** application tasks; no unsigned application image is launched. A systemd service launches digest-pinned Falco with the modern eBPF driver and sends JSON output to CloudWatch.

Falco is a host sensor: it needs powerful Linux capabilities and the Docker socket. Those privileges are intentionally isolated from the application. Kernel support and memory availability must be verified on the actual ECS host. `t3.micro` may be tight; if Falco is OOM-killed or drops events, review memory and consider `t3.small` only after reviewing its account eligibility/cost. Do not claim runtime protection until the sensor is healthy and an actual alert is recorded.

The bootstrap installs a systemd rule blocking bridge containers from host metadata. Check the rule again after host replacement/reboot. ECS app task credentials remain separate and grant no AWS permissions.

## 7. Pipeline stack

```bash
python scripts/provision.py pipeline
python scripts/provision.py pipeline --execute
```

The new V2 pipeline uses queued executions. GitHub source changes trigger:

1. Unit tests, template checks, selected Checkov controls, Guard, Semgrep and filesystem Trivy scan.
2. IAM Access Analyzer validation of actual role policies and the boundary. ERROR/SECURITY_WARNING blocks progress; other suggestions are saved.
3. Docker build, HIGH/CRITICAL vulnerability/secret gate and CycloneDX SBOM.
4. Unique immutable image tag, push to ECR and exact digest signing.
5. A separate CodeBuild role verifies source commit/digest, the trusted SSM public key, and task hardening before any ECS mutations.
6. Register the verified revision, update only this ECS service, wait for stability and reject rollback.

Inspect CloudWatch `/devsecops/devsecops-demo/build` and `/deploy` and the CodePipeline artifacts. A failing gate produces no deployment. The bootstrap ECR URI is deliberately not runnable and remains unused until the first verified release.

## 8. Application and runtime proof

Use an AWS CLI session on your Windows machine with the Session Manager plugin installed, or the Systems Manager Console for host commands. Find the instance ID in EC2 by the `devsecops-demo` name tag. No inbound SG changes are required.

```powershell
aws ssm start-session --region ap-south-1 --target i-REPLACE --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["8080"],"localPortNumber":["8080"]}'
```

Open `http://127.0.0.1:8080/health` on the client running the forwarding session. Do not expose port 8080 publicly to make the demo easier.

Inside the host's SSM shell, inspect the sensor and generate one harmless shell event in the demo app container:

```bash
sudo systemctl status project-falco --no-pager
sudo docker logs --tail 30 project-falco
APP_ID=$(sudo docker ps --filter name=app --format '{{.ID}}' | head -n 1)
test -n "$APP_ID"
sudo docker exec "$APP_ID" /bin/sh -c 'echo runtime-demo'
```

Check `/devsecops/devsecops-demo/falco` for the custom rule `Demo shell in application container`, then inspect the FalcoAlerts metric/alarm. Command execution alone is not proof of Falco detection. If missing, inspect sensor startup, mounts, kernel support, dropped events and log delivery.

Native CodePipeline execution events flow through EventBridge to `/devsecops/devsecops-demo/events`. Falco warnings generate CloudWatch metrics/alarms. CloudTrail **Event History** independently records management APIs; no persistent trail is created. Event History alone is not a CloudTrail-to-EventBridge streaming integration.

## 9. Drift and shutdown

```bash
python scripts/check-drift.py devsecops-demo-platform
python scripts/check-drift.py devsecops-demo-runtime
python scripts/stop-demo.py
```

Drift results are saved with all returned resources. CloudFormation detects only supported explicitly configured properties. Pipeline updates to the ECS service's task revision/DesiredCount intentionally differ from its zero-count bootstrap template; review these changes against `reports/deployment.json`, rather than claiming every runtime drift is malicious. Do not update the bootstrap runtime stack unchanged after deployment: it could reset the service to zero/old task. The provisioning helper deliberately refuses that update.

Shutdown first pauses the pipeline build transition, scales the app to zero, and scales the Auto Scaling group to zero. This avoids replacement EC2 instances. ECR, S3 and logs remain and can still incur storage costs. Resume with `python scripts/resume-demo.py`; it starts a fresh pipeline verification before restoring the application.

For full removal, export evidence, delete the pipeline stack then runtime stack then platform stack through CloudFormation. ECR and the artifact bucket are deliberately **retained**. Empty their objects/versions and remove them separately only after confirming that evidence can be destroyed. Remove the three signing parameters and the GitHub connection if no longer needed. Check Billing afterward. No destructive cleanup runs automatically.
