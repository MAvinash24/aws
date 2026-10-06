# Final implementation changes — 6 October 2026

The active release system is GitHub Actions. AWS continues to host ECR, ECS on EC2, SSM signing trust, Falco and CloudWatch. The independent local Docker app remains healthy at `http://127.0.0.1:8080/health`.

## Latest verified release

- [Workflow 37443610115](https://github.com/MAvinash24/aws/actions/runs/37443610115): both jobs succeeded.
- Source: `611b9ffc42a6671ff8778489f1ca8aa37f793823`.
- ECS task: `devsecops-demo:5`; one running HEALTHY task, zero pending, completed rollout.
- Digest: `sha256:6892e992a1ed76adc04b4783f1ac1248b1aa4e388bae4dac026b27c64b2cc58b`.
- 11 tests passed; selected Checkov 72 passed, zero failed/skipped/parsing errors; Semgrep zero findings/errors; strict image scan detected zero HIGH/CRITICAL CVEs or secrets.
- Both job check-runs have **zero annotations** after updating actions to native Node 24.
- AWS CLI 2.37.9 authenticated to the configured account and confirmed task revision 5.
- Fresh host inspection confirmed HTTP health, UID 10001, read-only rootfs, privileged false and ALL capabilities dropped. Falco remained active without OOM/restarts and delivered an actual new-task Warning to CloudWatch.

The supplied screenshots show earlier successful run 37438900114 and the pre-update warnings. They are retained and captioned as historical evidence in the report. The current results above are backed by newly downloaded run artifacts and AWS/CLI observations.

## File changes and their effects

| Files | Final change | Effect |
|---|---|---|
| `.github/workflows/deploy.yml` | Separate scan/build/sign and verify/deploy jobs; exact source and same-run artifact; OIDC; serialized releases; native Node 24 action pins | Avoid CodeBuild quota, preserve role separation and remove runtime deprecation warnings |
| `infra/generate.py`, `infra/github.json` | OIDC provider and bounded build/deploy roles with exact immutable repository/environment subjects | No stored AWS access keys in GitHub; correct trust for this repository |
| `infra/pipeline.json` | Source `DetectChanges=false` | Retained legacy pipeline does not auto-trigger on pushes |
| `scripts/provision.py`, `deploy.example.json` | GitHub stack and subject/provider configuration; `ci_provider=github` | Reviewable infrastructure and correct stop/resume path |
| `scripts/build-publish.sh` | CI-neutral release source/run identity, unique immutable tag and exact-digest signing | Shared secure publishing logic for active and legacy contexts |
| `scripts/deploy.py` | Accept GitHub release directory/source while retaining all verification | Signature/source/repository/task checks precede ECS changes |
| `scripts/validate-iam.py` | Include all eight role suffixes | Analyze actual GitHub and legacy role policies plus boundary |
| `scripts/security-gates.sh`, `scripts/check-project.py` | Cover all four templates and both role pairs | Include GitHub trust infrastructure in preventive validation |
| `scripts/install-tools.sh` | Configurable tool output directory | Hosted runner can install tools without system-directory writes |
| `scripts/github_api.py`, `stop-demo.py`, `resume-demo.py` | Credential Manager workflow control, cancel/wait before stopping, enable/dispatch on resume | Coordinate cloud compute with active GitHub CI |
| `docs/LOCAL-RUN-POWERSHELL.md`, `github-actions.md`, `deployment.md` | Current operating commands and active/legacy distinction | Avoid starting the inactive CodeBuild pipeline by mistake |
| `docs/report-build/`, `docs/report-assets/` | Editable content, reference-derived builder, five engineering diagrams and eight supplied screenshots | Maintainable illustrated capstone report |
| `deliverables/AWS_DevSecOps_Capstone_Report_Final.docx` | Academic report with confirmed author/institution/supervisor | Final submission artifact |

## AWS CLI checks

These are read-only and use the already configured credentials. This machine's AWS CLI is installed under the current user's Local AppData. Calling its full path avoids relying on a refreshed shell PATH.

```powershell
Set-Location D:\aws
$awsExe = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe'
& $awsExe --version
& $awsExe sts get-caller-identity --region ap-south-1
& $awsExe ecs describe-services --cluster devsecops-demo --services devsecops-demo --region ap-south-1 --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount,task:taskDefinition}' --output json
& $awsExe ecs list-tasks --cluster devsecops-demo --service-name devsecops-demo --region ap-south-1
```

AWS CLI and boto3 use the same configured account credentials. Updating the workflow changed the signed AWS release, not the CLI's credential identity or the runtime bootstrap stack. Do not reapply the runtime bootstrap template unchanged: it intentionally starts with zero tasks and an unused initial image.

## Docker and local checks

The application and Dockerfile did not change during the CI migration/runtime-warning fix. The existing local app remains valid and was kept running. AWS ECS now runs the newest signed release independently.

```powershell
Set-Location D:\aws
$dockerExe = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
& $dockerExe inspect --format '{{.State.Status}} {{.State.Health.Status}} {{.Config.User}} {{.HostConfig.ReadonlyRootfs}}' devsecops-local
Invoke-RestMethod http://127.0.0.1:8080/
Invoke-RestMethod http://127.0.0.1:8080/health
Get-Content .\reports\unit-tests.txt
```

For a complete local scan/build, use `scripts/validate-local.ps1` as documented in the local guide. It does not replace or stop `devsecops-local`. An updated vulnerability database can fail a later run; do not bypass a failing gate.

## Evidence and operating limits

New run artifacts are downloaded under `reports/github-run-37443610115/`. Current `reports/live-deployment.json`, `reports/deployment.json`, `reports/github-host-health.json`, `reports/github-falco-alert.json` and `reports/final-workflow-annotations.json` identify the final result. These changing machine-specific reports remain outside Git; the academic report and implementation summary are published.

CodeBuild's quota request remains a legacy issue; active GitHub CI does not require its approval. Source changes on `main` trigger releases. `README.md`, `docs/**` and `deliverables/**` changes alone are excluded. Manual **Run workflow** still works on `main`.

The existing AWS app and host remain running as requested. Runtime/storage continue to consume applicable credits or charges. The report describes selected scanner coverage, keyed signing without public transparency, one-host availability and the lack of a durable CloudTrail trail accurately.
