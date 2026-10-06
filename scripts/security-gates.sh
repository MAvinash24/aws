#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p reports
python -m unittest discover -s tests -v > reports/unit-tests.txt 2>&1
cat reports/unit-tests.txt
python scripts/check-project.py
cfn-lint -t infra/platform.json infra/runtime.json infra/pipeline.json infra/github.json
checkov --config-file security/checkov.yml --output json > reports/checkov.json
for template in infra/platform.json infra/runtime.json infra/pipeline.json infra/github.json; do
  cfn-guard validate --rules security/infrastructure.guard --data "$template" --show-summary all
done
cfn-guard test --rules-file security/infrastructure.guard --test-data security/guard-tests.yml
timeout 300 semgrep scan --config security/semgrep.yml --error --strict --jobs 2 --metrics=off --disable-version-check --json app scripts infra/generate.py > reports/semgrep.json
python scripts/test-semgrep.py
trivy fs --no-progress --scanners vuln,secret --severity HIGH,CRITICAL --exit-code 1 --skip-dirs .venv --skip-dirs .venv-linux --skip-dirs .tools --skip-dirs .secrets --skip-dirs reports --skip-dirs dist --format json --output reports/trivy-fs.json .
