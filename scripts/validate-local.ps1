$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) {
    $dockerPath = $dockerCommand.Source
} else {
    $dockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
    if (!(Test-Path -LiteralPath $dockerPath)) { throw 'Install/start Docker Desktop and put docker on PATH.' }
}
function Invoke-ProjectDocker {
    param([string[]]$DockerArguments)
    & $dockerPath @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker validation failed with exit code $LASTEXITCODE" }
}
New-Item -ItemType Directory -Path '.tools', '.tools\trivy-cache', 'reports' -Force | Out-Null
Invoke-ProjectDocker -DockerArguments @('build', '-f', 'Dockerfile.tools', '-t', 'devsecops-tools:local', '.')
# Scan an identical source copy on the Linux filesystem. Windows shared mounts
# can stall Semgrep's Git/file traversal. Reports are copied back even on failure.
$gateProgram = @'
set -Eeuo pipefail
mkdir -p /tmp/project
cp -r /source/app /source/scripts /source/infra /source/security /source/tests /source/requirements-tools.txt /source/Dockerfile /tmp/project/
cd /tmp/project
mkdir reports
trap 'cp -r reports/. /source/reports/' EXIT
bash scripts/security-gates.sh
'@
$sourceMount = "type=bind,source=$projectRoot,target=/source"
$cacheMount = "type=bind,source=$projectRoot\.tools\trivy-cache,target=/root/.cache/trivy"
Invoke-ProjectDocker -DockerArguments @('run', '--rm', '--mount', $sourceMount, '--mount', $cacheMount, 'devsecops-tools:local', '-lc', $gateProgram)
Invoke-ProjectDocker -DockerArguments @('build', '--pull', '-t', 'devsecops-app:local', '.')
Invoke-ProjectDocker -DockerArguments @('save', '-o', '.tools\app-image.tar', 'devsecops-app:local')
Invoke-ProjectDocker -DockerArguments @('run', '--rm', '--mount', $sourceMount, '--mount', $cacheMount, '--entrypoint', 'trivy', 'devsecops-tools:local', 'image', '--input', '/source/.tools/app-image.tar', '--no-progress', '--scanners', 'vuln,secret', '--severity', 'HIGH,CRITICAL', '--exit-code', '1', '--format', 'json', '--output', '/source/reports/trivy-image-local.json')
Write-Output 'Source, IaC, unit tests and application-image gates passed. Reports are in reports/.'
