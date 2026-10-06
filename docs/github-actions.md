# GitHub Actions deployment

GitHub Actions is the active CI/CD system for [MAvinash24/aws](https://github.com/MAvinash24/aws). CodeBuild's zero quota does not affect this workflow. The local Docker application remains independent at `http://127.0.0.1:8080/health`; AWS ECS remains on the existing EC2 host with Falco.

## Run an AWS release

Push application, infrastructure, security or workflow changes to `main`. Alternatively open [Actions](https://github.com/MAvinash24/aws/actions/workflows/deploy.yml), select **Run workflow**, choose `main`, and run it. Documentation-only pushes are excluded. A successful release requires both **Scan, build and sign** and **Verify and deploy to ECS** to pass.

The build job runs tests, generated-template checks, cfn-lint, selected Checkov controls, Guard and its rejection fixtures, Semgrep and its fixtures, and Trivy filesystem scanning. It then assumes the scoped build role, validates actual IAM policies, builds/scans the container, creates a CycloneDX SBOM, pushes an immutable ECR tag and signs its exact digest using the existing SSM key.

The deployment job has a separate role and runner. It downloads the manifest from the same workflow run, checks the source SHA and ECR repository/digest, fetches only the trusted public key, verifies the signature and task hardening, registers the verified digest and waits for ECS stability. A failed check or rollback fails the job.

Actions have pinned commit SHAs, security tools have pinned direct versions, and native tool downloads are checksum-verified. Reports and the release manifest are Actions artifacts retained for seven days; download evidence you need to keep longer. No signing private key or password is uploaded. Production workflow concurrency is one; an existing deployment is not automatically cancelled by a new push.

## AWS and GitHub setup

The existing platform/runtime/signing setup is described in [deployment.md](deployment.md). For a new account, create those resources first and check the costs. GitHub Actions does not need CodeConnections or CodeBuild. The retained legacy pipeline exists in this account but automatic source detection and the inbound build transition are disabled.

`infra/github.json` creates a GitHub OIDC provider and two roles under the existing permissions boundary. If the account already has `token.actions.githubusercontent.com`, supply its ARN as `github_oidc_provider_arn` rather than creating another provider. `github_oidc_subject_prefix` must match the repository's actual OIDC configuration; do not assume every repository uses the older name-only subject format.

This repository uses the immutable subject prefix `repo:MAvinash24@179509986/aws@1406786381`. The two accepted subjects end in `:environment:build` and `:environment:production`. Both trust policies require audience `sts.amazonaws.com`. Both GitHub environments allow only branch `main`. Pull requests and fork branches have no deployment trigger. Keep those environment branch restrictions and review workflow/security-policy changes before pushing to `main`.

For the configured local account:

```powershell
Set-Location D:\aws
.\.venv\Scripts\python.exe infra/generate.py
.\.venv\Scripts\python.exe scripts/provision.py github
```

Review `reports/changeset-github.json` and the actual IAM trust/permissions before execution. Use `--execute` only for an intended deployment. Do not update the bootstrap runtime stack unchanged after a release: it would reset the live ECS service.

In GitHub **Settings → Environments**, create `build` and `production`, each with custom deployment branch rule `main`. In **Settings → Secrets and variables → Actions → Variables**, configure:

| Repository variable | Value source |
|---|---|
| `AWS_ACCOUNT_ID` | Intended 12-digit AWS account |
| `ECR_URI` | Platform stack `RepositoryUri` output |
| `BOUNDARY_ARN` | Platform stack `BoundaryArn` output |
| `EXECUTION_ROLE_ARN` | Platform stack `ExecutionRoleArn` output |
| `TASK_ROLE_ARN` | Platform stack `TaskRoleArn` output |
| `AWS_BUILD_ROLE_ARN` | GitHub stack `GithubBuildRoleArn` output |
| `AWS_DEPLOY_ROLE_ARN` | GitHub stack `GithubDeployRoleArn` output |

These are identifiers, not secrets. AWS access keys are not stored in GitHub. The workflow receives short-lived AWS credentials via OIDC. Never grant AdministratorAccess to either role. Signing key/password remain in AWS SSM SecureString parameters; only the build role can read them.

## Stop or resume AWS later

Both local and AWS applications are intentionally left running. When finished, use:

```powershell
Set-Location D:\aws
.\.venv\Scripts\python.exe scripts/stop-demo.py --config deploy.local.json
```

With `ci_provider: github`, the helper uses your existing Git Credential Manager login to disable the workflow, cancel active runs and wait for them to finish before scaling AWS compute down. It also pauses the retained legacy pipeline. A GitHub access failure prevents compute shutdown. Stored images/logs still use storage. This command does not stop the local Docker app.

To resume:

```powershell
.\.venv\Scripts\python.exe scripts/resume-demo.py --config deploy.local.json
```

The helper restores the host, enables the GitHub workflow and dispatches a new signed release. Check the Actions run until both jobs pass. Re-enabling or pushing while intentionally stopped can restore the AWS app, so leave the workflow disabled until ready.

## Troubleshooting

| Failure | Check |
|---|---|
| AWS OIDC assumption denied | Actual subject prefix, audience, exact environment name, branch restriction and role ARN |
| Permission denied after role assumption | Failing API and exact role/boundary permissions; preserve build/deploy separation |
| Scan fails | Download evidence and remediate; do not ignore unfixed HIGH/CRITICAL issues |
| Signature fails | Expected SSM public key and exact ECR digest; do not accept keys from the artifact |
| ECS does not stabilize | ECS events, task health, host capacity and Falco memory; a rollback is a failed release |
| GitHub run cannot start | GitHub Actions repository/account settings and any billing/usage restriction; independent of AWS CodeBuild quota |

The public repository currently uses standard GitHub-hosted runners. Runner billing follows [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions); AWS runtime/storage charges remain separate.
