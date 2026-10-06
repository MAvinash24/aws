# Stop, restart or delete the AWS DevSecOps project

Prepared for Marisetti Avinash on 6 October 2026. Run these commands in **Windows PowerShell**. Choose the section you need; do not paste every section together. Creating this guide did not stop or delete anything.

| Choice | Result |
|---|---|
| Stop localhost | Local Python/Docker app stops; AWS continues |
| Stop AWS compute | Workflow disabled; ECS app and EC2 host scaled to zero; storage retained |
| Delete AWS project | Project stacks, retained images, bucket contents and signing parameters removed |
| Delete local images/files | Selected local artifacts removed; AWS unaffected |

## 1. Set paths and verify the AWS account

Use this setup in each new PowerShell window before the later commands.

```powershell
Set-Location D:\aws
$dockerExe = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$awsExe = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe'
$projectPython = 'D:\aws\.venv\Scripts\python.exe'
$region = 'ap-south-1'
$project = 'devsecops-demo'
$expectedAccount = '285150348444'
$env:AWS_PAGER = ''
& $awsExe sts get-caller-identity --region $region
if ($LASTEXITCODE -ne 0) { throw 'AWS authentication failed' }
$actualAccount = & $awsExe sts get-caller-identity --region $region --query Account --output text
if ($LASTEXITCODE -ne 0 -or $actualAccount.Trim() -ne $expectedAccount) {
    throw 'Wrong AWS account. Stop here.'
}
```

## 2. Stop localhost

### A. Stop the current Docker app

```powershell
& $dockerExe ps --filter name=devsecops-local
& $dockerExe stop devsecops-local
& $dockerExe ps -a --filter name=devsecops-local
```

The current container was started with `--rm`, so stopping it also removes the container. The image `devsecops-app:local` remains. An empty final listing is expected. If the container is already absent, the stop command reports that it does not exist.

### B. Stop a Python app started without Docker

Return to the PowerShell window running `python app/server.py` and press **Ctrl+C**. If that window is unavailable, identify the owner of port 8080 first:

```powershell
$listeners = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
$listeners | Select-Object LocalAddress,LocalPort,OwningProcess
$listeners | ForEach-Object {
    Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" |
        Select-Object ProcessId,Name,CommandLine
}
```

Only if the displayed command line is your project's Python server, replace `12345` with that process ID:

```powershell
Stop-Process -Id 12345
```

Do not stop a Docker backend process using its port owner; use `docker stop` for Docker containers.

### C. Verify localhost stopped

```powershell
try {
    Invoke-RestMethod http://127.0.0.1:8080/health -TimeoutSec 3
    Write-Output 'Something still answers on port 8080; inspect the listener.'
} catch {
    Write-Output 'Local health endpoint is unavailable, as expected after stopping.'
}
```

## 3. Restart the local Docker app

Start Docker Desktop if its engine is stopped. Do not run a Python server on the same port.

```powershell
& $dockerExe run --detach --rm --name devsecops-local --publish 127.0.0.1:8080:8080 --read-only --cap-drop ALL --security-opt no-new-privileges devsecops-app:local
Start-Sleep -Seconds 10
Invoke-RestMethod http://127.0.0.1:8080/health
& $dockerExe inspect --format '{{.State.Status}} {{.State.Health.Status}}' devsecops-local
```

Health may initially show `starting`; repeat the inspect after about 30 seconds. If the image was deleted, rebuild it first:

```powershell
& $dockerExe build --pull -t devsecops-app:local D:\aws
```

## 4. Stop AWS compute while keeping the project

This is the normal choice when you want to save compute costs and resume later. The existing script checks the account, disables GitHub deployment, cancels/waits for active workflow runs, pauses the legacy pipeline, scales ECS to zero and scales its Auto Scaling group to zero. It needs the existing Git Credential Manager login and `deploy.local.json`.

```powershell
Set-Location D:\aws
& $projectPython scripts/stop-demo.py --config deploy.local.json
if ($LASTEXITCODE -ne 0) { throw 'Shutdown failed. Inspect the error before continuing.' }
```

**Do not stop the EC2 instance directly:** Auto Scaling can replace it. Scaling the group to zero terminates its host; resuming creates a replacement. ECR images, S3 objects, logs and signing parameters remain, and retained storage can still incur charges.

Verify the result:

```powershell
& $awsExe ecs describe-services --cluster $project --services $project --region $region --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount}' --output json
& $awsExe autoscaling describe-auto-scaling-groups --region $region --query "AutoScalingGroups[?starts_with(AutoScalingGroupName, 'devsecops-demo-runtime-')].{name:AutoScalingGroupName,min:MinSize,desired:DesiredCapacity,instances:length(Instances)}" --output table
& $awsExe ec2 describe-instances --region $region --filters 'Name=tag:Name,Values=devsecops-demo' 'Name=instance-state-name,Values=pending,running,stopping,stopped,shutting-down' --query 'Reservations[].Instances[].{id:InstanceId,state:State.Name}' --output table
```

Expected ECS desired/running/pending: `0/0/0`. Host termination may take a few minutes. Do not manually re-enable the workflow while keeping AWS stopped.

## 5. Resume AWS after section 4

```powershell
Set-Location D:\aws
& $projectPython scripts/resume-demo.py --config deploy.local.json
if ($LASTEXITCODE -ne 0) { throw 'Resume failed; inspect the error.' }
```

This creates/resumes host capacity, enables the GitHub workflow and requests a new signed deployment. Follow [GitHub Actions](https://github.com/MAvinash24/aws/actions/workflows/deploy.yml), then check ECS:

```powershell
& $awsExe ecs describe-services --cluster $project --services $project --region $region --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount,task:taskDefinition}' --output json
```

## 6. Permanently delete the AWS project

**This destroys project resources and, in the retained-storage step, images, signatures and all S3 object versions. Resume commands will no longer work; provisioning is required to rebuild.** Keep your report/source/evidence outside `D:\aws` before also deleting local files. Existing packages are `D:\aws\dist\aws-devsecops-source.zip` and `D:\aws\dist\aws-live-evidence.zip`.

### 6.1 Stop automation and compute first

Run section 1, then section 4 successfully. Do this **before deleting any stacks**, because the stop script needs them. Keep the workflow disabled afterward.

Capture the exact retained bucket and connection before deleting stack outputs:

```powershell
$artifactBucket = & $awsExe cloudformation describe-stacks --stack-name "$project-platform" --region $region --query "Stacks[0].Outputs[?OutputKey=='ArtifactBucket'].OutputValue | [0]" --output text
if ($LASTEXITCODE -ne 0 -or $artifactBucket -ne 'devsecops-demo-platform-artifacts-ixmxwurgqnnv') {
    throw 'Unexpected artifact bucket; inspect the stack outputs before deleting.'
}
$connectionArn = (Get-Content D:\aws\deploy.local.json -Raw | ConvertFrom-Json).connection_arn
Write-Output $artifactBucket
Write-Output $connectionArn
```

### 6.2 Delete the four CloudFormation stacks in order

```powershell
foreach ($stack in @('devsecops-demo-github','devsecops-demo-pipeline','devsecops-demo-runtime','devsecops-demo-platform')) {
    Write-Output "Deleting $stack"
    & $awsExe cloudformation delete-stack --stack-name $stack --region $region
    if ($LASTEXITCODE -ne 0) { throw "Delete request failed: $stack" }
    & $awsExe cloudformation wait stack-delete-complete --stack-name $stack --region $region
    if ($LASTEXITCODE -ne 0) { throw "Deletion did not complete: $stack. Inspect stack events before continuing." }
}
```

CloudFormation removes stack-managed compute, roles, CodeBuild/CodePipeline, security groups, logs and alarms. The project's ECR repository and artifact bucket are deliberately retained. The existing default VPC/subnet and administrator IAM user are outside these stacks and remain.

If a stack fails to delete, inspect the failure instead of using force deletion:

```powershell
& $awsExe cloudformation describe-stack-events --stack-name 'REPLACE_WITH_FAILED_STACK_NAME' --region $region --query 'StackEvents[?ResourceStatus==`DELETE_FAILED`].{resource:LogicalResourceId,reason:ResourceStatusReason}' --output table
```

### 6.3 Deregister remaining app task revisions, then delete retained ECR

Deployments register task revisions outside CloudFormation. After the service is deleted, deregister remaining active revisions of this exact family. Inactive task-definition records do not run containers or incur compute charges.

```powershell
$taskJson = & $awsExe ecs list-task-definitions --family-prefix $project --status ACTIVE --region $region --output json
if ($LASTEXITCODE -ne 0) { throw 'Cannot list task revisions' }
$taskList = ($taskJson -join "`n") | ConvertFrom-Json
foreach ($taskArn in $taskList.taskDefinitionArns) {
    if ($taskArn -match ':task-definition/devsecops-demo:\d+$') {
        & $awsExe ecs deregister-task-definition --task-definition $taskArn --region $region
        if ($LASTEXITCODE -ne 0) { throw 'Cannot deregister task revision' }
    }
}
```

Delete the repository and its images/signatures:

```powershell
& $awsExe ecr describe-repositories --repository-names $project --region $region
& $awsExe ecr delete-repository --repository-name $project --force --region $region
if ($LASTEXITCODE -ne 0) { throw 'ECR deletion failed' }
```

### 6.4 Permanently empty the versioned artifact bucket, then delete it

Run in the same PowerShell session as 6.1. This removes **versions and delete markers**, which ordinary `aws s3 rm --recursive` does not fully remove from a versioned bucket. The loop processes bounded batches and stops on errors.

```powershell
if ($artifactBucket -ne 'devsecops-demo-platform-artifacts-ixmxwurgqnnv') { throw 'Bucket guard failed' }
$deleteBatchFile = 'D:\aws\reports\delete-artifact-batch.json'
do {
    $versionJson = & $awsExe s3api list-object-versions --bucket $artifactBucket --expected-bucket-owner $expectedAccount --region $region --max-keys 500 --no-paginate --output json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot list bucket versions' }
    $versionPage = ($versionJson -join "`n") | ConvertFrom-Json
    $objects = @()
    foreach ($entry in @($versionPage.Versions) + @($versionPage.DeleteMarkers)) {
        if ($null -ne $entry) { $objects += @{ Key = $entry.Key; VersionId = $entry.VersionId } }
    }
    if ($objects.Count -gt 0) {
        $batchJson = @{ Objects = @($objects); Quiet = $true } | ConvertTo-Json -Depth 6
        [System.IO.File]::WriteAllText($deleteBatchFile, $batchJson, (New-Object System.Text.UTF8Encoding($false)))
        $deletedJson = & $awsExe s3api delete-objects --bucket $artifactBucket --expected-bucket-owner $expectedAccount --region $region --delete file://D:/aws/reports/delete-artifact-batch.json --output json
        if ($LASTEXITCODE -ne 0) { throw 'Object deletion request failed' }
        $deleted = ($deletedJson -join "`n") | ConvertFrom-Json
        if (@($deleted.Errors).Where({ $null -ne $_ }).Count -gt 0) { throw ($deleted.Errors | ConvertTo-Json -Depth 6) }
        Write-Output "Deleted $($objects.Count) object versions/delete markers"
    }
} while ($objects.Count -gt 0)

# Abort any incomplete uploads before deleting the bucket.
do {
    $uploadJson = & $awsExe s3api list-multipart-uploads --bucket $artifactBucket --expected-bucket-owner $expectedAccount --region $region --max-uploads 500 --no-paginate --output json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot list incomplete uploads' }
    $uploadPage = ($uploadJson -join "`n") | ConvertFrom-Json
    $uploads = @($uploadPage.Uploads) | Where-Object { $null -ne $_ }
    foreach ($upload in $uploads) {
        & $awsExe s3api abort-multipart-upload --bucket $artifactBucket --key $upload.Key --upload-id $upload.UploadId --expected-bucket-owner $expectedAccount --region $region
        if ($LASTEXITCODE -ne 0) { throw 'Cannot abort incomplete upload' }
    }
} while (@($uploads).Count -gt 0)

& $awsExe s3api delete-bucket --bucket $artifactBucket --expected-bucket-owner $expectedAccount --region $region
if ($LASTEXITCODE -ne 0) { throw 'Bucket deletion failed' }
```

### 6.5 Delete signing parameters and the project connection

```powershell
& $awsExe ssm delete-parameters --names /devsecops-demo/signing/private-key /devsecops-demo/signing/password /devsecops-demo/signing/public-key --region $region
```

Deleting private signing material prevents future use of that key unless you have an independent backup. Existing image verification requires the public key; retain a copy if you need historical verification.

Delete the following connection only if it is still dedicated to this project and no other pipeline uses it:

```powershell
if ($connectionArn -ne 'arn:aws:codeconnections:ap-south-1:285150348444:connection/3cc45dac-12b3-4acf-839e-e1fe1e612bb2') { throw 'Connection guard failed' }
& $awsExe codeconnections delete-connection --connection-arn $connectionArn --region $region
```

The GitHub OIDC provider is stack-managed if this project created it; an externally supplied/shared provider must remain. Do not delete shared OIDC providers, the AWS IAM login user or the GitHub repository as part of project cleanup.

### 6.6 Verify AWS removal

```powershell
& $awsExe cloudformation list-stacks --region $region --query "StackSummaries[?starts_with(StackName, 'devsecops-demo-')].{name:StackName,state:StackStatus}" --output table
& $awsExe ecr describe-repositories --repository-names $project --region $region
& $awsExe s3api head-bucket --bucket $artifactBucket --expected-bucket-owner $expectedAccount --region $region
& $awsExe ssm describe-parameters --region $region --parameter-filters 'Key=Name,Option=BeginsWith,Values=/devsecops-demo/signing/' --query 'Parameters[].Name' --output json
& $awsExe ec2 describe-instances --region $region --filters 'Name=tag:Name,Values=devsecops-demo' 'Name=instance-state-name,Values=pending,running,stopping,stopped,shutting-down' --query 'Reservations[].Instances[].{id:InstanceId,state:State.Name}' --output table
```

Expected: project stacks `DELETE_COMPLETE`, repository not found, bucket absent, signing-parameter list empty and no active project instances. For `head-bucket`, a 403 is **not proof of deletion**; it can mean permission failure. Inspect Billing/Cost Explorer afterward; billing data can lag, and account-wide resources unrelated to this project are outside this cleanup.

## 7. Delete only local Docker images

Stop the app using section 2 first, then remove the project's images:

```powershell
& $dockerExe image ls
& $dockerExe image rm devsecops-app:local
# Optional: remove the project scanner/tool image too.
& $dockerExe image rm devsecops-tools:local
```

If another container uses an image, Docker refuses removal; inspect that container before removing it. This leaves Docker Desktop installed. To quit its engine, use the Docker Desktop tray menu **Quit Docker Desktop** after stopping your containers. Do not use `docker system prune -a --volumes` for this project cleanup: it can delete other projects' data.

## 8. Optional: remove the complete local project folder

Do this **last**, after AWS cleanup if required, and after saving your DOCX, source archive and evidence elsewhere. It removes source files, local signing-test files, reports, the Python environment and Git checkout. It does not uninstall Docker or AWS CLI, remove AWS resources, revoke credentials or delete the GitHub repository.

```powershell
Set-Location D:\
$projectFolderToDelete = (Resolve-Path -LiteralPath 'D:\aws').Path
if ($projectFolderToDelete -ne 'D:\aws') { throw 'Unexpected folder; refusing deletion' }
Get-Item -LiteralPath $projectFolderToDelete
# Run the next line only when you want to destroy this local folder.
Remove-Item -LiteralPath $projectFolderToDelete -Recurse -Force
```

There is no localhost resource to delete separately: localhost is your machine's loopback address. Stop its listening process/container, and delete the corresponding image/files only if desired. AWS CLI is a client; deleting or uninstalling it does not stop AWS charges. Keep it available until AWS removal is verified.

## Official command references

- [CloudFormation deletion waiter](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/cloudformation/wait/stack-delete-complete.html)
- [ECR repository deletion](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/ecr/delete-repository.html)
- [S3 version deletion semantics](https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObject.html)
- [S3 version listing](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/list-object-versions.html)

**Shortest stop sequence:** initialize paths in section 1, run `docker stop devsecops-local`, then run `scripts/stop-demo.py`. **Permanent deletion:** complete section 6 in order, then sections 7 and 8 only if you also want local data removed.
