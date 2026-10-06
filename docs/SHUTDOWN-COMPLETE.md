# Verified project shutdown and deletion

Completed on **6 October 2026 at 4:38 PM IST**, following the owner's request. AWS account `285150348444`, region `ap-south-1`.

| Item | Verified result |
|---|---|
| Local Docker app `devsecops-local` | Stopped; auto-remove container absent |
| Localhost port 8080 | No listener |
| EC2 `i-0acb79567665cb804` | Terminated |
| Root disk `vol-0af8ce21bc3cdae2b` | Deleted |
| Four `devsecops-demo-*` CloudFormation stacks | All `DELETE_COMPLETE` |
| ECS cluster/service and Auto Scaling group | Removed |
| ECR `devsecops-demo` | Repository, cloud images and signatures deleted |
| S3 `devsecops-demo-platform-artifacts-ixmxwurgqnnv` | All three versions/delete markers removed; bucket deleted |
| Project signing parameters | All three deleted |
| Dedicated AWS GitHub connection | Deleted |
| Project CloudWatch log groups | Removed |
| GitHub deployment workflow | `disabled_manually`; zero active runs |
| GitHub Actions artifact storage | All nine artifacts deleted; zero remaining |
| GitHub repository | Preserved for source/report access |
| Local `D:\aws`, DOCX and evidence packages | Preserved |
| Docker images `devsecops-app:local`, `devsecops-tools:local` | Both preserved |

Verification is recorded in `D:\aws\reports\cleanup-verification.json`; deleted artifact metadata is in `reports/deleted-github-artifacts.json`. Earlier deployment evidence and the capstone DOCX describe the historical successful release. The local evidence ZIP remains available after the online workflow artifacts were deleted.

No active project EC2 host, root disk, S3 bucket, ECR repository, ECS cluster, Auto Scaling group, signing parameter, dedicated connection or project log group remained at verification. No allocated Elastic IPs or EBS volumes remained in the checked region. An unrelated empty `RDSOSMetrics` log group was left unchanged.

This removes the identified project resources; it does not erase charges already accrued or cancel unrelated account services/subscriptions. Billing data may update later.

To run locally again, start Docker Desktop and use section 3 of [the command guide](STOP-AND-DELETE-POWERSHELL.md). To recreate AWS, provision infrastructure and initialize new signing trust before enabling GitHub deployment. `resume-demo.py` alone cannot restore deleted stacks.
