# Validation evidence — 6 October 2026

## Verified locally

| Check | Result |
|---|---|
| Unit/integration logic tests | 11 passed: HTTP behavior, signature-before-mutation ordering, digest/repository/source validation, hardening, rollback and account/project preflight |
| CloudFormation schema/lint | All four templates passed cfn-lint 1.57.1 |
| Generated templates | Match the editable `infra/generate.py` source |
| IAM role separation | Build cannot update ECS or pass roles; deploy cannot push/sign/read the private key |
| Checkov 3.3.23 | 72 checks passed; 0 failures, skipped checks or parsing errors within the selected control set |
| CloudFormation Guard 3.2.1 | Applicable rules passed across all four templates; five intentionally unsafe fixtures rejected as expected |
| Semgrep CE 1.179.0 | 0 findings/errors on application, Python scripts and infrastructure generator; five annotated unsafe fixture cases correctly identified and safe cases not flagged |
| Trivy 0.75.0 filesystem scan | Passed configured HIGH/CRITICAL vulnerability/secret gate; demo application has no third-party dependency manifest |
| Trivy application image scan | Passed with 0 detected HIGH/CRITICAL vulnerabilities or secrets using the downloaded database; pinned Alpine 3.23 Python runtime |
| Hardened application container | `/health` succeeds; UID 10001; read-only rootfs and dropped capabilities. Write rejection observed during container validation |
| Real Cosign 3.1.3 signatures | Disposable localhost OCI registry: unsigned rejected, correct public key accepted, wrong public key rejected |
| Falco publisher integrity | Official release-tag signature verified with the expected GitHub issuer/workflow identity; Linux amd64 sensor digest pinned |
| YAML/shell/PowerShell source | YAML and shell syntax checked; PowerShell helper parsed successfully |

The first Debian application image failed the strict CVE gate. It was replaced with the pinned Alpine image and rescanned; the gate was not weakened, unfixed findings were not ignored, and the rejected report remains locally as `reports/trivy-image-rejected-debian.json`.

Semgrep stalled while traversing the Windows shared filesystem. The same source was copied into the validation container's Linux filesystem and scanned successfully. `scripts/validate-local.ps1` uses that arrangement. Security gate commands use strict errors and timeouts rather than accepting partial scans.

Native scanner downloads were checked against committed SHA-256 digests. A failed empty package download was rejected by pip's hash verification, then downloaded again successfully. Checkov's native Windows extension was blocked by host application control, so Checkov was executed in the Linux validation image.

## Local evidence files

Reports are excluded from Git to keep changing machine-specific scan output out of the source repository:

* `reports/unit-tests.txt`
* `reports/checkov.json`
* `reports/semgrep.json`
* `reports/trivy-fs.json`
* `reports/trivy-image-local.json`
* `reports/trivy-image-rejected-debian.json`
* `reports/signing-local.json`

These results apply to the checked-in source/base image and the scanner database used at validation time. Future databases or changes can fail the gate.

## Verified in AWS

Local shared-profile credentials successfully authenticated to the intended account. AWS account-aware change-set validation passed before provisioning. The platform, runtime and pipeline stacks completed in Mumbai; later policy updates also completed.

| Check | Live result |
|---|---|
| GitHub connection and source retrieval | AVAILABLE connection; source stage succeeded for the repository |
| IAM Access Analyzer | Actual eight-role policies and boundary validated without errors or security warnings; ECS condition-type warning corrected |
| Connection policy | Exact connection and repository/branch context; explicit provider-write denial. IAM simulator allows expected reads and rejects other repositories/writes |
| ECR | AES256 encryption, immutable tags, scan-on-push; attempted replacement of an existing tag rejected with ImageTagAlreadyExistsException |
| Initial release | Locally built and scanned image pushed to real ECR; zero detected HIGH/CRITICAL vulnerabilities or secrets; SBOM saved |
| Signing and verification | Real ECR OCI reference signature accepted by trusted SSM public key; wrong key rejected by deployment verifier before ECS mutation |
| ECS | Exact verified digest deployed; one running HEALTHY task, zero pending tasks; HTTP health endpoint succeeds via SSM |
| Application hardening | UID 10001, read-only root filesystem, no privileged mode, ALL capabilities dropped; IMDS token request blocked from the application |
| EC2/Falco | Amazon Linux 2023 modern eBPF sensor active; no OOM or restarts during checks; sensor memory approximately 57 MiB |
| Runtime detection | Harmless shell execution in the actual application produced a Warning event in CloudWatch and the Falco alarm entered ALARM |
| EventBridge | Native pipeline execution events delivered to the project's CloudWatch event log group |
| Audit | CloudTrail management-event history queried; no durable trail configured |
| CloudFormation drift | Platform and pipeline IN_SYNC. Runtime DRIFTED only at the service's desired count and task revision, which the verified deployment intentionally changed |

The initial release was deployed from the authenticated administrator's local setup session using the same signature-before-mutation verifier. **It was not produced by a successful CodeBuild execution.** Local reports contain the source SHA, image digest, task revision, scan results, signing rejection evidence and real runtime outputs.

The live drift check exposed a boto3 API detail: `DescribeStackResourceDrifts` returns `NextToken` but has no generated paginator. The utility now follows those tokens explicitly and preserves a separate report for each stack. Do not redeploy the runtime bootstrap template to make the drift report green: it would reset the service to zero tasks and the unsigned placeholder revision.

## Legacy CodeBuild restriction (avoided by active CI)

CodeBuild returned `AccountLimitExceededException: Cannot have more than 0 builds in queue for the account`. Applied concurrency quotas are zero. The request to raise Linux/Small concurrency to one is `CASE_OPENED` and awaits AWS review. The legacy AWS-managed build/deploy stages have not run successfully. The active GitHub Actions pipeline completed both jobs successfully and does not require this quota. The legacy trigger and inbound build transition are disabled.

Both the AWS application and independent local Docker application remain running for demonstration. Use the documented stop command when finished to conserve credits. No billing-plan change, paid security trial, NAT gateway or load balancer was enabled.

Reports include `reports/deployment.json`, `reports/bootstrap-release-summary.json`, `reports/trivy-image-bootstrap.json`, `reports/sbom-bootstrap.cdx.json`, `reports/iam-validation.json`, `reports/ecr-immutable-overwrite-live.json`, `reports/ecr-basic-scan-live.json`, `reports/wrong-signature-live.json`, `reports/application-health-hardening-live.json`, `reports/falco-application-alert-live.json`, `reports/eventbridge-delivery-live.json`, `reports/codebuild-quota-request-status.json`, and per-stack drift results.

## Successful GitHub Actions release

[Run 37436946485](https://github.com/MAvinash24/aws/actions/runs/37436946485) completed with **success** for source `5a7723206201d0287082b8b12258b5e81eeb8947`. Both **Scan, build and sign** and **Verify and deploy to ECS** passed, including every security gate, real OIDC role assumption, deployed IAM policy validation, ECR publish/signing, trusted-key verification and ECS stability checks.

The verified image is `285150348444.dkr.ecr.ap-south-1.amazonaws.com/devsecops-demo@sha256:df9b6527beb27b3a8498246a2037bb031d2140a0ce8851c18016237f95b3bd13`, deployed as task definition `devsecops-demo:3`. The host HTTP health check succeeded; the app runs as UID 10001, read-only, unprivileged, with ALL capabilities dropped. Falco remained active with zero restarts and no OOM. Harmless shell probes in the new task produced two actual Warning events in CloudWatch; evidence is saved in `reports/github-falco-alert.json`. The local `devsecops-local` container remained running and healthy on localhost:8080 throughout.

AWS IAM simulation denied `ecs:UpdateService` for the GitHub build role and denied private-signing-key reads for the GitHub deploy role. The exact immutable repository/environment subjects and `sts.amazonaws.com` audience successfully authenticated both roles; environment branch rules allow only `main`. No stored AWS access keys were added to GitHub.

Run logs and all three release/build/deployment artifacts are available in GitHub Actions for seven days, with downloaded copies under `reports/github-run-37436946485/`. Additional local evidence includes `reports/github-oidc-configuration.json`, `reports/github-role-separation-live.json` and `reports/github-host-health.json` and `reports/github-falco-alert.json`. Documentation-only pushes do not redeploy.
