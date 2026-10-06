# Run the project locally — Windows PowerShell

Yes, you can run this project locally. Your screenshot already shows the correct folder: `PS D:\aws>`.

Copy commands from the blocks below. Do not copy the `PS D:\aws>` prompt. Choose either the Python app or the Docker app; both use port 8080, so stop one before starting the other.

Local application, tests, scanners and signing tests do not require AWS credentials or CodeBuild capacity. AWS-only commands are clearly separated at the end.

**Current deployment:** GitHub Actions handles AWS releases without CodeBuild. The existing local container can stay running while Actions deploys to ECS. See [GitHub setup and run instructions](github-actions.md).

## 1. Open the project

```powershell
Set-Location D:\aws
Get-ChildItem
Test-Path .\.venv\Scripts\python.exe
```

The last command should return `True`. The prepared folder already contains the Python environment. You do not need to activate it: the commands call its Python directly.

If you move only the source to another computer, create an environment with an installed Python first:

```powershell
py -3 -m venv .venv
```

The application uses Python's standard library and needs no pip installation to run.

## 2. Run the application directly with Python

In your first PowerShell window:

```powershell
Set-Location D:\aws
$env:HOST = '127.0.0.1'
$env:PORT = '8080'
.\.venv\Scripts\python.exe -m app.server
```

The command keeps running. It may show no message until you send a request; this is expected. Keep this window open.

Open a second PowerShell window and run:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/
Start-Process 'http://127.0.0.1:8080/health'
```

Expected health response: `status: healthy`. The root endpoint returns the project name and version. This project is a small JSON HTTP service, so the browser shows JSON rather than a graphical dashboard.

To stop the application, return to the first window and press **Ctrl+C**.

## 3. Run the application tests and project checks

```powershell
Set-Location D:\aws
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/check-project.py
```

Expected results: `Ran 11 tests`, `OK`, and `Project consistency and permission separation: PASS`.

These tests also exercise deployment-verification logic with mocked AWS calls. They do not deploy AWS resources.

## 4. Run the hardened application in Docker

Stop the Python app first. Start **Docker Desktop** from the Windows Start menu and wait until its Linux engine is running.

Resolve Docker's executable in the current PowerShell window:

```powershell
Set-Location D:\aws
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) {
    $dockerExe = $dockerCommand.Source
} else {
    $dockerExe = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
}
& $dockerExe version
```

The output should contain both Client and Server details. Then build and start the app:

```powershell
& $dockerExe build --pull -t devsecops-app:local .
& $dockerExe run --detach --rm --name devsecops-local --publish 127.0.0.1:8080:8080 --read-only --cap-drop ALL --security-opt no-new-privileges devsecops-app:local
```

Check it:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
& $dockerExe logs devsecops-local
& $dockerExe inspect --format '{{.State.Health.Status}}' devsecops-local
& $dockerExe exec devsecops-local python -c 'import os; print(os.geteuid())'
```

Expected: healthy response, Docker health eventually `healthy`, and UID `10001`. Docker health can initially be `starting`; wait approximately 30 seconds and repeat the inspect command.

Stop the local container:

```powershell
& $dockerExe stop devsecops-local
```

Because it was started with `--rm`, Docker removes the container after it stops. Its built image remains available.

## 5. Run all local security gates

Keep Docker Desktop running. From PowerShell:

```powershell
Set-Location D:\aws
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate-local.ps1
```

`-ExecutionPolicy Bypass` applies to this child PowerShell process; it does not change your permanent execution-policy setting.

The helper builds the Linux tools image, runs unit tests, checks generated templates, runs cfn-lint, Checkov, Guard and Semgrep, scans the filesystem with Trivy, builds the application image, and scans that image. Downloads require internet access. The first run can take several minutes; later runs reuse caches. Linux containers avoid the Windows-native scanner issues encountered during setup.

Success ends with:

```text
Source, IaC, unit tests and application-image gates passed. Reports are in reports/.
```

Read the reports:

```powershell
Get-ChildItem .\reports
Get-Content .\reports\unit-tests.txt
Get-Content .\reports\semgrep.json
Get-Content .\reports\trivy-image-local.json
```

A new vulnerability database can produce new failures. Treat a scanner failure as a failed gate; do not change exit codes or ignore findings just to make the demonstration pass.

## 6. Optional: test real local image signing

Run section 5 first, so `devsecops-app:local` exists. Run the Docker executable-resolution block from section 4 in this window if `$dockerExe` is not set.

```powershell
Set-Location D:\aws
$cosignExe = (Resolve-Path .\.tools\cosign.exe).Path
.\.venv\Scripts\python.exe scripts/test-signing-local.py --docker $dockerExe --cosign $cosignExe
Get-Content .\reports\signing-local.json
```

This starts a temporary registry reachable only through localhost port 15000. It generates disposable keys and verifies that an unsigned image is rejected, the trusted key is accepted, and a wrong key is rejected. It cleans up its registry and temporary keys. It does not use the AWS production signing parameters.

## 7. What is local and what remains on AWS?

| Component | Local demonstration |
|---|---|
| Application | Python or hardened Docker container |
| Unit tests and IaC/security scanners | Existing local scripts and Linux tools container |
| Cosign signing | Disposable local OCI registry test |
| GitHub Actions | Active remote CI; local scripts run the same scan/verification logic |
| CodePipeline / CodeBuild | Retained inactive legacy infrastructure |
| IAM Access Analyzer / ECR / ECS / EventBridge | Remain AWS integrations |
| Falco kernel detection | Verified on the AWS Linux host; ordinary Windows PowerShell does not reproduce that Linux eBPF environment |

Running locally does not stop the existing AWS host. Local tests alone do not prove a successful managed CodePipeline execution.

## 8. CodeBuild quota: is the account causing it?

Checked live on **6 October 2026** in **Mumbai (`ap-south-1`)**:

- Applied Linux/Small concurrency quota (`L-9D07B6EF`): **0**.
- Requested quota: **1**, sufficient because build and deploy run sequentially.
- Request status: **CASE_OPENED**.
- AWS support case: **179127073800023**.

Yes: this particular failure is an **AWS account-and-region service quota restriction**. The source stage succeeds; CodeBuild cannot start because the account has no build capacity. AdministratorAccess does not create capacity or override that limit.

AWS documents that its internal metrics determine concurrency defaults and that those limits can vary. Account-specific restrictions are possible, but zero is not proof that your account is defective. AWS has not provided the exact reason here, so it would be inaccurate to blame it specifically on account age, incomplete verification, or the Free Plan. See [AWS CodeBuild quotas](https://docs.aws.amazon.com/codebuild/latest/userguide/limits.html).

Review the existing request in [Mumbai Service Quotas](https://ap-south-1.console.aws.amazon.com/servicequotas/home?region=ap-south-1#!/services/codebuild/quotas) and [AWS Support Center](https://support.console.aws.amazon.com/support/home#/case/?displayId=179127073800023). Do not submit duplicate requests. The Support API requires a support subscription in this account; you can use the browser Support Center to inspect any response. No support-plan purchase or billing-plan change has been made.

## 9. Optional AWS checks — requires your configured credentials

These commands contact AWS. If using a newly created local environment instead of this prepared folder, first install its SDK:

```powershell
.\.venv\Scripts\python.exe -m pip install boto3==1.35.49
```

Check identity and the applied quota:

```powershell
Set-Location D:\aws
.\.venv\Scripts\python.exe -c "import boto3; print(boto3.client('sts', region_name='ap-south-1').get_caller_identity()['Arn'])"
.\.venv\Scripts\python.exe -c "import boto3; q=boto3.client('service-quotas', region_name='ap-south-1').get_service_quota(ServiceCode='codebuild', QuotaCode='L-9D07B6EF'); print(q['Quota']['Value'])"
```

To run the active AWS release, open [GitHub Actions](https://github.com/MAvinash24/aws/actions/workflows/deploy.yml), select **Run workflow**, choose `main`, and run it. Check both jobs: **Scan, build and sign** and **Verify and deploy to ECS**. CodeBuild quota approval is not required. Do not start the retained legacy CodePipeline alongside the active workflow.

## 10. Optional: stop AWS compute while using the local app

This changes AWS: it disables the GitHub workflow, cancels/waits for active jobs, pauses the legacy pipeline, stops the AWS application and scales the demo host to zero. Local Python/Docker remain independent.

```powershell
Set-Location D:\aws
.\.venv\Scripts\python.exe scripts/stop-demo.py --config deploy.local.json
```

Stored ECR images, S3 artifacts and logs remain and may still consume storage credits. Git Credential Manager must already be signed into GitHub to disable/cancel the workflow. To restore AWS compute and request a new GitHub Actions deployment:

```powershell
.\.venv\Scripts\python.exe scripts/resume-demo.py --config deploy.local.json
```

## Troubleshooting

| Symptom | Action |
|---|---|
| Port 8080 already in use | Stop your Python app with Ctrl+C or stop `devsecops-local`; do not run both together |
| `docker` not recognized | Use `$dockerExe` from section 4; the helper also locates this Docker Desktop installation automatically |
| Docker cannot connect to its server | Start Docker Desktop and wait for the Linux engine |
| Container name already in use | Inspect `& $dockerExe ps -a --filter name=devsecops-local`; stop the previous demo container before rerunning |
| `.venv` Python not found | Check the current folder or create the environment as described in section 1 |
| Scan fails | Read the reported failure and corresponding `reports/` file; do not bypass the gate |
| CodeBuild still reports capacity zero | The active GitHub Actions workflow avoids CodeBuild; leave the legacy pipeline disabled |
