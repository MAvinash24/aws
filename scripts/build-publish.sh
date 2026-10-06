#!/usr/bin/env bash
set -Eeuo pipefail
: "${ECR_URI:?}" "${ECR_NAME:?}" "${PROJECT_NAME:?}" "${AWS_DEFAULT_REGION:?}"
# Unique per execution: rebuilding a commit does not overwrite immutable tags.
build_uuid="${CODEBUILD_BUILD_ID##*:}"
image_tag="${CODEBUILD_RESOLVED_SOURCE_VERSION:0:12}-$build_uuid"
image="$ECR_URI:$image_tag"
docker build --pull -t "$image" .
trivy image --no-progress --scanners vuln,secret --severity HIGH,CRITICAL --exit-code 1 --format json --output reports/trivy-image.json "$image"
trivy image --format cyclonedx --output reports/sbom.cdx.json "$image"
aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "${ECR_URI%%/*}"
docker push "$image"
digest=$(aws ecr describe-images --repository-name "$ECR_NAME" --image-ids "imageTag=$image_tag" --query 'imageDetails[0].imageDigest' --output text)
[[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid digest'; exit 1; }
export IMAGE_DIGEST_URI="$ECR_URI@$digest"
secret_dir=$(mktemp -d)
chmod 700 "$secret_dir"
trap 'unset COSIGN_PASSWORD; rm -rf -- "$secret_dir"' EXIT
# Never use shell tracing here. Secret values are not printed or artifacts.
aws ssm get-parameter --name "/$PROJECT_NAME/signing/private-key" --with-decryption --query Parameter.Value --output text > "$secret_dir/cosign.key"
chmod 600 "$secret_dir/cosign.key"
COSIGN_PASSWORD=$(aws ssm get-parameter --name "/$PROJECT_NAME/signing/password" --with-decryption --query Parameter.Value --output text)
export COSIGN_PASSWORD
export COSIGN_EXPERIMENTAL=1
# Private keyed signing; Rekor publication intentionally disabled. See trust model.
cosign sign --yes --key "$secret_dir/cosign.key" --signing-config security/cosign-signing.json --registry-referrers-mode=oci-1-1 "$IMAGE_DIGEST_URI"
python -c 'import json, os; from pathlib import Path; Path("release.json").write_text(json.dumps({"image": os.environ["IMAGE_DIGEST_URI"], "source": os.environ["CODEBUILD_RESOLVED_SOURCE_VERSION"]}), encoding="utf-8")'
