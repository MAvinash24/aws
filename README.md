# AWS DevSecOps student implementation

A small application and a complete AWS deployment scaffold for Problem Statement 10. GitHub repository: [MAvinash24/aws](https://github.com/MAvinash24/aws). Region: Mumbai (`ap-south-1`).

**Live status, 6 October 2026:** All three stacks are deployed in Mumbai. A locally scanned, signed and verified initial release is healthy in ECS; real Falco application alerts reach CloudWatch. GitHub source retrieval works. **The managed build/deploy pipeline remains blocked by the account's zero CodeBuild concurrency quota.** A request for one Linux/Small build is awaiting AWS review. See [validation evidence](docs/validation.md); a successful end-to-end CodePipeline run has not yet been demonstrated.

## Architecture

```mermaid
flowchart TD
  GitHub[GitHub main branch] --> Pipeline[CodePipeline V2]
  Pipeline --> Build[CodeBuild: tests / Checkov / cfn-lint / Guard / Semgrep / Trivy]
  Build --> Image[Build container / Trivy HIGH + CRITICAL gate / SBOM]
  Image --> ECR[ECR: immutable tags / BASIC scan-on-push]
  ECR --> Sign[Cosign: sign exact digest]
  Sign --> Release[release.json: digest + source commit]
  Release --> Verify[Separate CodeBuild role: IAM validation / trusted-key signature verification]
  Verify --> ECS[ECS on one EC2 instance]
  ECS --> App[Non-root / read-only / no capabilities / no AWS permissions]
  ECS --> Falco[Falco modern eBPF on Linux host]
  Falco --> Logs[CloudWatch JSON logs / metric / alarm]
  Pipeline --> Events[Native pipeline events to EventBridge to CloudWatch Logs]
  Audit[CloudTrail Event History: independent 90-day API audit]
```

AWS resources can incur charges. Open-source security tools remove product subscriptions and trials; they do not make EC2, public IPv4, EBS, S3, ECR, builds, or logs unconditionally free. Confirm your account's eligibility, credit balance and billing limits before provisioning. No NAT gateway, load balancer, EKS cluster, customer-managed KMS key, Inspector, GuardDuty, Security Hub, Config recorder or Control Tower landing zone is created.

## Files

| Location | Purpose |
|---|---|
| `app/`, `Dockerfile` | Dependency-free HTTP demo, `/health`, non-root container, digest-pinned base |
| `infra/platform.json` | ECR, artifact bucket, logs, IAM boundary and runtime roles, alerting |
| `infra/runtime.json` | Existing VPC/subnet, one encrypted EC2 ECS host, Falco, zero-count bootstrap service |
| `infra/pipeline.json` | GitHub CodeConnection input, V2 pipeline, separate CodeBuild roles |
| `infra/generate.py` | Editable source for the three templates; regenerate after changing it |
| `security/` | Guard rules and rejection fixtures, Semgrep rules, Checkov scope, version/checksum locks |
| `scripts/` | Scan, build, sign, verify/deploy, provisioning, drift and stop/resume commands |
| `docs/deployment.md` | Step-by-step console and terminal setup |
| `docs/trust-and-costs.md` | Trust boundary, substitutions, limits and billing considerations |

## Run locally (PowerShell)

```powershell
Set-Location D:\aws
python -m unittest discover -s tests -v
python scripts/check-project.py
python -m app.server
```

Open [the local health check](http://127.0.0.1:8080/health). Stop the server with Ctrl+C. This demonstrates application behavior, not an AWS deployment.

With Docker Desktop running and `docker` on your PATH:

```powershell
.\scripts\validate-local.ps1
docker run --rm -p 127.0.0.1:8080:8080 --read-only --cap-drop ALL --security-opt no-new-privileges devsecops-app:local
```

The PowerShell helper runs scans on the container's Linux filesystem to avoid slow Windows file traversal, builds the app, and scans the saved image. It exits on any gate failure. On Linux/CodeBuild, image scanning uses the local Docker image directly:

```bash
trivy image --scanners vuln,secret --severity HIGH,CRITICAL --exit-code 1 devsecops-app:local
```

Never add `--ignore-unfixed`, `|| true`, or `--exit-code 0` to get a passing demonstration. A new HIGH/CRITICAL finding must fail the gate even when the base image currently has no vendor fix.

## Deploy

Follow [deployment instructions](docs/deployment.md). The project uses an existing GitHub repository and an authorized GitHub CodeConnection. The source branch is `main`. Confirm that CodeBuild's applied Linux/Small concurrency quota is at least one before starting the managed pipeline.

The managed deployment stage validates IAM policies, verifies the trusted-key signature for the exact repository digest, and checks task hardening before starting the container. The initial release used the same verifier from the administrator's local setup session while CodeBuild capacity was unavailable. The build role cannot deploy; the deploy role cannot sign or push images. Local tests explicitly check rejection and rollback behavior.

## Assignment substitutions

| Assignment service | Implemented demonstration | Important difference |
|---|---|---|
| CodeGuru Reviewer | Semgrep CE with checked-in rules | Static patterns; no CodeGuru ML/concurrency parity |
| Inspector | Trivy filesystem and image gates + ECR BASIC scan | CI snapshot; no managed continuous vulnerability service |
| AWS Signer | Cosign keyed signing in ECR OCI reference artifacts | Independent signing system; trust and key management are yours |
| Control Tower/SCPs | Scoped roles + IAM boundaries + Access Analyzer + Guard | Single account; boundaries are not organization-wide SCPs |
| GuardDuty runtime | Falco modern eBPF | Host/container detection; no managed account threat intelligence |
| Security Hub | CloudWatch log/metric/alarm + native EventBridge pipeline events | Monitoring, not a centralized CSPM finding service |
| AWS Config | Guard prevention + on-demand CloudFormation drift script | Not continuous compliance; only supported resource properties |

These substitutions preserve the proposed project demonstration goals. They do **not** satisfy a rubric requiring those exact managed products; obtain your instructor's agreement to the replacements.
