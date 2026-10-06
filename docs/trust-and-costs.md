# Implementation limits and trust

## Signature trust

The trusted public key lives in SSM under a separately authorized administrator. Deployment never accepts a public key from the release artifact. The release manifest is untrusted input: repository, SHA-256 digest and full source commit are checked. Verification precedes registration/update, and ECS receives the digest rather than a mutable tag.

Cosign stores OCI 1.1 reference artifacts in ECR. Each build has a unique image tag. The checked-in `cosign-signing.json` selects private keyed signing with no Rekor or timestamping services. Verification uses `--insecure-ignore-tlog=true` to disable the transparency-log requirement while retaining cryptographic signature and digest verification. This does not disable TLS or signature checking. The pinned Cosign version requires `COSIGN_EXPERIMENTAL=1` for OCI 1.1 registry referrers; both stages set it explicitly. This demonstration proves artifact integrity relative to the trusted key, not public transparency or independent build provenance.

Signing and deployment roles are separate. A compromised build identity can sign an image using the build key; the signature alone does not establish that its source is safe. The release branch, buildspecs, scanner rules, role policies and SSM key writes must be trusted and reviewed. ECS has no built-in Cosign admission policy here. An administrator or another principal with direct ECS deployment permissions can bypass the normal pipeline. The IAM boundary applies to project roles, not to root/admin or the entire account.

The application grants no AWS API permissions, runs as UID 10001, has a read-only filesystem, and drops all Linux capabilities. Falco uses host-level capabilities and Docker-socket access as required by its sensor. Host compromise can affect the application and monitoring; Falco is detection, not sandbox enforcement or automatic remediation.

## Scanner scope

Checkov uses the explicitly selected controls in `security/checkov.yml`, covering bucket encryption/privacy/versioning, SG descriptions/open access, ECR scanning and IAM/container concerns. Checkov rule availability must be checked against the pinned version. Guard adds project-specific invariants and rejection fixtures. Run a full Checkov scan separately when expanding the project; do not call this selected control set an exhaustive security audit.

Semgrep's checked-in rules detect dynamic evaluation, shell execution and disabled TLS. They are intentionally small, reviewable demonstration rules, not the full Semgrep registry or a replacement for human code review. Trivy scans source/dependencies/secrets and the built application image, and blocks every detected HIGH/CRITICAL finding without ignoring unfixed issues. Vulnerability results depend on database freshness and vendor severity data. ECR BASIC OS scanning is supplementary and does not block independently in this implementation.

Python scanner packages have pinned direct versions; their transitive resolution is not fully hash-locked. Native Cosign, Trivy and Guard assets are version-pinned and SHA-256 verified against committed official release digests. These are reproducibility controls, not a claim of complete supply-chain provenance. The application has no third-party Python dependencies.

## Correct monitoring flows

* Falco JSON → CloudWatch Logs → metric filter → CloudWatch alarm.
* Native CodePipeline events → EventBridge → CloudWatch Logs.
* CloudTrail Event History → console/API audit lookup.
* CloudFormation → explicitly requested drift detection → evidence JSON.

There is no implicit CloudWatch Logs → EventBridge forwarding, and EventBridge is not an upstream source of CloudTrail audit events. A CloudTrail management-event streaming integration generally requires a configured trail; this project retains Event History only. There is no continuous AWS Config or Security Hub posture management, alert email, auto-remediation, or multi-account governance.

## Costs

No paid security trial service is mandatory. EC2 instance hours, EBS, public IPv4, artifact/image storage, build/pipeline execution, data transfer, CloudWatch logs/alarms and SSM features remain subject to AWS account eligibility, quotas, credits and pricing. The design avoids NAT and ALB charges, uses seven-day log retention, expires old pipeline artifacts and runs one host. ECR has no lifecycle policy to delete old digests automatically because it could remove the active deployment or associated signature. Monitor storage and prune only retired releases after checking current ECS task references.

Budget alerts are notifications, not guaranteed hard spending caps. Stopping the instance manually is insufficient while an Auto Scaling group wants one host; use `stop-demo.py` to scale it to zero. Retained data can still incur costs after stack deletion.

The [AWS Free Tier FAQ](https://aws.amazon.com/free/free-tier-faqs/) describes credit/plan limits and the impact of joining Organizations/Control Tower. Confirm the actual account's status instead of relying on quoted historic free-tier allowances.

## Primary references

* [AWS GitHub CodeConnections source action](https://docs.aws.amazon.com/codepipeline/latest/userguide/connections-github.html)
* [AWS ECR OCI artifacts](https://docs.aws.amazon.com/AmazonECR/latest/userguide/images.html)
* [AWS IAM permissions boundaries](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
* [AWS Access Analyzer policy checks](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-reference-policy-checks.html)
* [AWS ECS authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecs.html)
* [Falco container installation and capabilities](https://falco.org/docs/setup/container/)
* [Cosign signing/verification](https://docs.sigstore.dev/cosign/signing/signing_with_containers/)
* [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html)
