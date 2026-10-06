# Validation evidence — 6 October 2026

## Verified locally

| Check | Result |
|---|---|
| Unit/integration logic tests | 11 passed: HTTP behavior, signature-before-mutation ordering, digest/repository/source validation, hardening, rollback and account/project preflight |
| CloudFormation schema/lint | All three templates passed cfn-lint 1.57.1 |
| Generated templates | Match the editable `infra/generate.py` source |
| IAM role separation | Build cannot update ECS or pass roles; deploy cannot push/sign/read the private key |
| Checkov 3.3.23 | 58 checks passed; 0 failures, skipped checks or parsing errors within the selected control set |
| CloudFormation Guard 3.2.1 | Applicable rules passed across all three templates; five intentionally unsafe fixtures rejected as expected |
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

## Live AWS verification is pending

AWS Console sign-in in Mumbai was confirmed. CloudShell then returned:

> Unable to create the environment. Your account verification is in progress. This may take up to two days for new accounts.

No project AWS resources were created, and no claim is made that the AWS pipeline, IAM Access Analyzer API, ECR immutability/referrers, ECS host, SSM forwarding, actual Falco kernel detection, CloudWatch alert delivery, or drift detection has run successfully in this account.

The localhost signature test verifies Cosign's real OCI signing path; it is not a substitute for an ECR integration test. Deployment tests use mocked ECS calls and cannot establish the behavior of a live AWS service. Falco publisher verification does not establish sensor/kernel compatibility or actual runtime alerts.

After account verification, follow `docs/deployment.md`, authorize the GitHub connection, review/execute the three stack change sets, initialize signing trust, and record a full pipeline execution plus real Falco alert before presenting live completion.
