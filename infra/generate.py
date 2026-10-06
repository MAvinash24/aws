"""Generate editable CloudFormation JSON; no AWS calls or resource creation."""
import json
import copy
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ref(name):
    return {"Ref": name}


def sub(value):
    return {"Fn::Sub": value}


def att(name, attribute="Arn"):
    return {"Fn::GetAtt": [name, attribute]}


def statement(actions, resources, **extra):
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def document(statements):
    return {"Version": "2012-10-17", "Statement": statements}


def resource(kind, **properties):
    return {"Type": "AWS::" + kind, "Properties": properties}


def base(description):
    return {"AWSTemplateFormatVersion": "2010-09-09", "Description": description,
            "Metadata": {"AWSToolsMetrics": {"AWSAgentToolkit": "aws-cloudformation@3"},
                         "com.aws.cloudformation.Context": {"ref": ["docs/trust-and-costs.md", "docs/deployment.md"]}},
            "Parameters": {"ProjectName": {"Type": "String", "Default": "devsecops-demo", "AllowedPattern": "[a-z][a-z0-9-]{2,23}"}},
            "Resources": {}, "Outputs": {}}


def output(template, name, value):
    template["Outputs"][name] = {"Value": value}


def role(service, suffix, boundary, statements):
    return resource("IAM::Role", RoleName=sub("${ProjectName}-" + suffix),
                    PermissionsBoundary=boundary,
                    AssumeRolePolicyDocument=document([{"Effect": "Allow", "Principal": {"Service": service}, "Action": ["sts:AssumeRole"]}]),
                    Policies=[{"PolicyName": "ProjectPermissions", "PolicyDocument": document(statements)}])


def log_group(suffix):
    return resource("Logs::LogGroup", LogGroupName=sub("/devsecops/${ProjectName}/" + suffix), RetentionInDays=7)


def bucket():
    return resource("S3::Bucket", BucketEncryption={"ServerSideEncryptionConfiguration": [{"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
                    PublicAccessBlockConfiguration={"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True},
                    OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
                    VersioningConfiguration={"Status": "Enabled"},
                    LifecycleConfiguration={"Rules": [{"Id": "OldArtifacts", "Status": "Enabled", "ExpirationInDays": 14, "NoncurrentVersionExpiration": {"NoncurrentDays": 7}, "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}}]})


def bucket_policy(name):
    return resource("S3::BucketPolicy", Bucket=ref(name), PolicyDocument=document([{
        "Effect": "Deny", "Principal": "*", "Action": ["s3:*"],
        "Resource": [att(name), sub("${" + name + ".Arn}/*")],
        "Condition": {"Bool": {"aws:SecureTransport": "false"}}
    }]))


def generate_platform():
    t = base("DevSecOps platform: ECR, private artifacts, bounded IAM, logs and alerts. Usage may cost money.")
    r = t["Resources"]
    r["Repository"] = resource("ECR::Repository", RepositoryName=ref("ProjectName"), ImageTagMutability="IMMUTABLE",
                              ImageScanningConfiguration={"ScanOnPush": True}, EncryptionConfiguration={"EncryptionType": "AES256"})
    # Preserve evidence/images if the stack is accidentally deleted.
    r["Repository"].update(DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    r["Artifacts"] = bucket()
    r["Artifacts"].update(DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    r["ArtifactsPolicy"] = bucket_policy("Artifacts")
    for name, suffix in [("BuildLogs", "build"), ("DeployLogs", "deploy"), ("AppLogs", "app"), ("FalcoLogs", "falco"), ("EventLogs", "events")]:
        r[name] = log_group(suffix)
    repo = att("Repository")
    logs = sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/devsecops/${ProjectName}/*:*")
    artifacts = [att("Artifacts"), sub("${Artifacts.Arn}/*")]
    signing = sub("arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/${ProjectName}/signing/*")
    role_arns = sub("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/${ProjectName}-*")
    policy_arn = sub("arn:${AWS::Partition}:iam::${AWS::AccountId}:policy/${ProjectName}-boundary")
    cluster = sub("arn:${AWS::Partition}:ecs:${AWS::Region}:${AWS::AccountId}:cluster/${ProjectName}")
    service = sub("arn:${AWS::Partition}:ecs:${AWS::Region}:${AWS::AccountId}:service/${ProjectName}/${ProjectName}")
    family = sub("arn:${AWS::Partition}:ecs:${AWS::Region}:${AWS::AccountId}:task-definition/${ProjectName}:*")
    instance = sub("arn:${AWS::Partition}:ecs:${AWS::Region}:${AWS::AccountId}:container-instance/${ProjectName}/*")
    region_condition = {"StringEquals": {"aws:RequestedRegion": ref("AWS::Region")}}
    ecs_agent = [statement(["ecs:DiscoverPollEndpoint"], "*", Condition=region_condition),
                 statement(["ecs:Poll", "ecs:StartTelemetrySession", "ecs:DeregisterContainerInstance", "ecs:PutAttributes"], instance),
                 statement(["ecs:RegisterContainerInstance", "ecs:SubmitAttachmentStateChanges", "ecs:SubmitContainerStateChange", "ecs:SubmitTaskStateChange"], cluster)]
    ssm_agent = ["ssm:UpdateInstanceInformation", "ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel"]
    boundary_stmts = [
        statement(["logs:CreateLogStream", "logs:PutLogEvents"], logs),
        statement(["s3:GetBucketLocation", "s3:GetBucketVersioning", "s3:ListBucket", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"], artifacts),
        statement(["ecr:GetAuthorizationToken", "access-analyzer:ValidatePolicy"], "*"),
        statement(["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:DescribeImages"], repo),
        statement(["ssm:GetParameter"], signing),
        statement(["kms:Decrypt"], "*", Condition={"StringEquals": {"kms:ViaService": sub("ssm.${AWS::Region}.amazonaws.com")}}),
        statement(["iam:ListRolePolicies", "iam:GetRolePolicy"], role_arns),
        statement(["iam:GetPolicy", "iam:GetPolicyVersion"], policy_arn),
        statement(["codeconnections:UseConnection"], sub("arn:${AWS::Partition}:codeconnections:${AWS::Region}:${AWS::AccountId}:connection/*")),
        statement(["codebuild:StartBuild", "codebuild:BatchGetBuilds"], sub("arn:${AWS::Partition}:codebuild:${AWS::Region}:${AWS::AccountId}:project/${ProjectName}-*")),
        statement(["ecs:RegisterTaskDefinition"], family, Condition={"StringEquals": {"ecs:privileged": "false"}}),
        statement(["ecs:DescribeTaskDefinition"], "*"),
        statement(["ecs:DescribeServices", "ecs:UpdateService"], service),
        statement(["iam:PassRole"], role_arns, Condition={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}),
        *ecs_agent,
        statement(ssm_agent, "*", Condition=region_condition),
    ]
    r["Boundary"] = resource("IAM::ManagedPolicy", ManagedPolicyName=sub("${ProjectName}-boundary"), PolicyDocument=document(boundary_stmts))
    boundary = ref("Boundary")
    r["ExecutionRole"] = role("ecs-tasks.amazonaws.com", "execution", boundary, [
        statement(["ecr:GetAuthorizationToken"], "*"),
        statement(["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], repo),
        statement(["logs:CreateLogStream", "logs:PutLogEvents"], logs),
    ])
    # Empty identity policy: app has no AWS API permissions.
    r["TaskRole"] = role("ecs-tasks.amazonaws.com", "task", boundary, [])
    del r["TaskRole"]["Properties"]["Policies"]
    r["HostRole"] = role("ec2.amazonaws.com", "host", boundary, [
        *ecs_agent,
        statement(ssm_agent, "*", Condition=region_condition),
        statement(["ecr:GetAuthorizationToken"], "*"),
        statement(["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], repo),
        statement(["logs:CreateLogStream", "logs:PutLogEvents"], logs),
    ])
    r["HostProfile"] = resource("IAM::InstanceProfile", Roles=[ref("HostRole")])
    r["LogDeliveryPolicy"] = resource("Logs::ResourcePolicy", PolicyName=sub("${ProjectName}-events"), PolicyDocument=document([{
        "Effect": "Allow", "Principal": {"Service": "events.amazonaws.com"}, "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource": att("EventLogs"), "Condition": {"ArnEquals": {"aws:SourceArn": att("PipelineEvents")}, "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")}}
    }]))
    r["PipelineEvents"] = resource("Events::Rule", EventPattern={"source": ["aws.codepipeline"], "detail-type": ["CodePipeline Pipeline Execution State Change"], "detail": {"pipeline": [ref("ProjectName")], "state": ["FAILED", "SUCCEEDED", "CANCELED"]}},
                                   State="ENABLED", Targets=[{"Id": "Logs", "Arn": sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/devsecops/${ProjectName}/events")}])
    r["FalcoMetric"] = resource("Logs::MetricFilter", LogGroupName=ref("FalcoLogs"), FilterPattern='{ $.priority = "Warning" || $.priority = "Error" || $.priority = "Critical" || $.priority = "Alert" || $.priority = "Emergency" }',
                               MetricTransformations=[{"MetricNamespace": sub("DevSecOps/${ProjectName}"), "MetricName": "FalcoAlerts", "MetricValue": "1", "DefaultValue": 0}])
    r["FalcoAlarm"] = resource("CloudWatch::Alarm", AlarmDescription="Falco warning or higher detected. Inspect the Falco log group.", Namespace=sub("DevSecOps/${ProjectName}"), MetricName="FalcoAlerts", Statistic="Sum", Period=60, EvaluationPeriods=1, Threshold=1, ComparisonOperator="GreaterThanOrEqualToThreshold", TreatMissingData="notBreaching")
    for name, value in {"RepositoryUri": att("Repository", "RepositoryUri"), "RepositoryArn": repo, "ArtifactBucket": ref("Artifacts"), "BoundaryArn": boundary,
                        "ExecutionRoleArn": att("ExecutionRole"), "TaskRoleArn": att("TaskRole"), "HostProfileArn": att("HostProfile")}.items():
        output(t, name, value)
    return t


def generate_runtime():
    t = base("Single EC2 ECS host, no inbound ports, app starts only after signature verification.")
    t["Parameters"].update({
        "VpcId": {"Type": "AWS::EC2::VPC::Id"}, "SubnetId": {"Type": "AWS::EC2::Subnet::Id", "Description": "Public subnet with internet route; no NAT gateway is created."},
        "HostProfileArn": {"Type": "String"}, "ExecutionRoleArn": {"Type": "String"}, "TaskRoleArn": {"Type": "String"},
        "InstanceType": {"Type": "String", "Default": "t3.micro", "AllowedValues": ["t3.micro", "t3.small"]},
        "EcsAmi": {"Type": "AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>", "Default": "/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id"},
        "InitialImage": {"Type": "String", "Description": "ECR URI placeholder; service DesiredCount is zero until verified deployment."},
        "FalcoImage": {"Type": "String", "Default": "falcosecurity/falco:0.45.0", "Description": "Pin a verified Falco digest before live setup."},
    })
    r = t["Resources"]
    r["Cluster"] = resource("ECS::Cluster", ClusterName=ref("ProjectName"), ClusterSettings=[{"Name": "containerInsights", "Value": "disabled"}])
    r["HostSecurityGroup"] = resource("EC2::SecurityGroup", GroupDescription="No inbound access. Use SSM port forwarding.", VpcId=ref("VpcId"), SecurityGroupIngress=[],
                                     SecurityGroupEgress=[{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0", "Description": "HTTPS to AWS APIs and image registries"}])
    bootstrap = '''#!/bin/bash
set -Eeuo pipefail
cat >> /etc/ecs/ecs.config <<'ECS'
ECS_CLUSTER=${ProjectName}
ECS_AWSVPC_BLOCK_IMDS=true
ECS_ENABLE_TASK_IAM_ROLE=true
ECS_ENABLE_TASK_IAM_ROLE_NETWORK_HOST=false
ECS
# Prevent bridge-network application tasks from reaching the instance role.
cat > /etc/systemd/system/project-imds-block.service <<'IMDS'
[Unit]
Description=Block application access to host instance credentials
After=docker.service
Requires=docker.service
Before=ecs.service
[Service]
Type=oneshot
ExecStart=/bin/bash -c '/usr/sbin/iptables -C DOCKER-USER -i docker+ -d 169.254.169.254/32 -j DROP || /usr/sbin/iptables -I DOCKER-USER -i docker+ -d 169.254.169.254/32 -j DROP'
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
IMDS
systemctl daemon-reload
systemctl enable --now project-imds-block
mkdir -p /etc/falco
cat > /etc/falco/project_rules.yaml <<'RULES'
- rule: Demo shell in application container
  desc: Demonstration of unexpected shell execution in a container
  condition: spawned_process and container and proc.name in (sh, bash, dash, zsh)
  output: "Unexpected shell in container (user=%user.name command=%proc.cmdline container=%container.id)"
  priority: WARNING
  tags: [process, container, demo]
RULES
cat > /etc/systemd/system/project-falco.service <<'UNIT'
[Unit]
Description=DevSecOps Falco runtime monitor
After=docker.service network-online.target
Requires=docker.service
[Service]
Restart=always
RestartSec=15
ExecStartPre=-/usr/bin/docker rm -f project-falco
ExecStart=/usr/bin/docker run --name project-falco --cap-drop ALL --cap-add SYS_ADMIN --cap-add SYS_RESOURCE --cap-add SYS_PTRACE --security-opt no-new-privileges --memory 384m --mount type=bind,source=/sys/kernel/tracing,target=/sys/kernel/tracing,readonly --mount type=bind,source=/var/run/docker.sock,target=/host/var/run/docker.sock --mount type=bind,source=/proc,target=/host/proc,readonly --mount type=bind,source=/etc,target=/host/etc,readonly --mount type=bind,source=/etc/falco/project_rules.yaml,target=/etc/falco/falco_rules.local.yaml,readonly --log-driver awslogs --log-opt awslogs-region=${AWS::Region} --log-opt awslogs-group=/devsecops/${ProjectName}/falco --log-opt awslogs-stream=host --log-opt awslogs-create-group=false ${FalcoImage} falco -o engine.kind=modern_ebpf -o json_output=true -o stdout_output.enabled=true
ExecStop=/usr/bin/docker stop project-falco
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now project-falco
'''
    r["HostTemplate"] = resource("EC2::LaunchTemplate", LaunchTemplateData={
        "ImageId": ref("EcsAmi"), "InstanceType": ref("InstanceType"), "IamInstanceProfile": {"Arn": ref("HostProfileArn")},
        "MetadataOptions": {"HttpTokens": "required", "HttpEndpoint": "enabled", "HttpPutResponseHopLimit": 1},
        "BlockDeviceMappings": [{"DeviceName": "/dev/xvda", "Ebs": {"Encrypted": True, "VolumeType": "gp3", "VolumeSize": 30, "DeleteOnTermination": True}}],
        "NetworkInterfaces": [{"DeviceIndex": 0, "AssociatePublicIpAddress": True, "Groups": [ref("HostSecurityGroup")]}],
        "CreditSpecification": {"CpuCredits": "standard"}, "UserData": {"Fn::Base64": sub(bootstrap)}})
    r["Hosts"] = resource("AutoScaling::AutoScalingGroup", MinSize="1", MaxSize="1", DesiredCapacity="1", VPCZoneIdentifier=[ref("SubnetId")],
                          LaunchTemplate={"LaunchTemplateId": ref("HostTemplate"), "Version": att("HostTemplate", "LatestVersionNumber")},
                          Tags=[{"Key": "Name", "Value": ref("ProjectName"), "PropagateAtLaunch": True}])
    r["Task"] = resource("ECS::TaskDefinition", Family=ref("ProjectName"), NetworkMode="bridge", RequiresCompatibilities=["EC2"], ExecutionRoleArn=ref("ExecutionRoleArn"), TaskRoleArn=ref("TaskRoleArn"),
                         ContainerDefinitions=[{"Name": "app", "Image": ref("InitialImage"), "Essential": True, "Memory": 128, "Cpu": 128, "User": "10001:10001", "Privileged": False,
                                                "ReadonlyRootFilesystem": True, "LinuxParameters": {"Capabilities": {"Drop": ["ALL"]}},
                                                "PortMappings": [{"ContainerPort": 8080, "HostPort": 8080, "Protocol": "tcp"}],
                                                "HealthCheck": {"Command": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"], "Interval": 30, "Timeout": 3, "Retries": 3, "StartPeriod": 10},
                                                "LogConfiguration": {"LogDriver": "awslogs", "Options": {"awslogs-group": sub("/devsecops/${ProjectName}/app"), "awslogs-region": ref("AWS::Region"), "awslogs-stream-prefix": "app"}}}])
    r["Service"] = resource("ECS::Service", ServiceName=ref("ProjectName"), Cluster=ref("Cluster"), LaunchType="EC2", DesiredCount=0, TaskDefinition=ref("Task"),
                            DeploymentConfiguration={"MinimumHealthyPercent": 0, "MaximumPercent": 100, "DeploymentCircuitBreaker": {"Enable": True, "Rollback": True}})
    output(t, "ClusterName", ref("Cluster"))
    output(t, "ServiceName", ref("ProjectName"))
    output(t, "AutoScalingGroup", ref("Hosts"))
    return t


def generate_pipeline():
    t = base("GitHub connection to CodePipeline V2 with separate build and verifying deploy roles.")
    t["Parameters"].update({
        "ConnectionArn": {"Type": "String", "AllowedPattern": "arn:[^:]+:codeconnections:[^:]+:[0-9]{12}:connection/.+", "Description": "Existing AVAILABLE GitHub CodeConnection. Authorize GitHub installation manually."},
        "FullRepositoryId": {"Type": "String", "AllowedPattern": "[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"}, "BranchName": {"Type": "String", "Default": "main"},
        "ArtifactBucket": {"Type": "String"}, "RepositoryUri": {"Type": "String"}, "RepositoryArn": {"Type": "String"},
        "BoundaryArn": {"Type": "String"}, "ExecutionRoleArn": {"Type": "String"}, "TaskRoleArn": {"Type": "String"},
    })
    r = t["Resources"]
    logs = sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/devsecops/${ProjectName}/*:*")
    artifacts = [sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}"), sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}/*")]
    common = [statement(["logs:CreateLogStream", "logs:PutLogEvents"], logs), statement(["s3:GetBucketLocation", "s3:GetBucketVersioning", "s3:ListBucket", "s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"], artifacts)]
    iam_read = [statement(["access-analyzer:ValidatePolicy"], "*"), statement(["iam:ListRolePolicies", "iam:GetRolePolicy"], sub("arn:${AWS::Partition}:iam::${AWS::AccountId}:role/${ProjectName}-*")), statement(["iam:GetPolicy", "iam:GetPolicyVersion"], ref("BoundaryArn"))]
    r["BuildRole"] = role("codebuild.amazonaws.com", "build", ref("BoundaryArn"), common + iam_read + [
        statement(["ecr:GetAuthorizationToken"], "*"),
        statement(["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:DescribeImages"], ref("RepositoryArn")),
        statement(["ssm:GetParameter"], [sub("arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/${ProjectName}/signing/private-key"), sub("arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/${ProjectName}/signing/password")]),
        statement(["kms:Decrypt"], "*", Condition={"StringEquals": {"kms:ViaService": sub("ssm.${AWS::Region}.amazonaws.com")}}),
    ])
    r["DeployRole"] = role("codebuild.amazonaws.com", "deploy", ref("BoundaryArn"), common + iam_read + [
        statement(["ecr:GetAuthorizationToken"], "*"), statement(["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], ref("RepositoryArn")),
        statement(["ssm:GetParameter"], sub("arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/${ProjectName}/signing/public-key")),
        statement(["ecs:RegisterTaskDefinition"], sub("arn:${AWS::Partition}:ecs:${AWS::Region}:${AWS::AccountId}:task-definition/${ProjectName}:*"), Condition={"StringEquals": {"ecs:privileged": "false"}}), statement(["ecs:DescribeTaskDefinition"], "*"),
        statement(["ecs:DescribeServices", "ecs:UpdateService"], sub("arn:${AWS::Partition}:ecs:${AWS::Region}:${AWS::AccountId}:service/${ProjectName}/${ProjectName}")),
        statement(["iam:PassRole"], [ref("ExecutionRoleArn"), ref("TaskRoleArn")], Condition={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}),
    ])
    environment = [{"Name": "PROJECT_NAME", "Value": ref("ProjectName")}, {"Name": "ECR_URI", "Value": ref("RepositoryUri")}, {"Name": "ECR_NAME", "Value": ref("ProjectName")},
                   {"Name": "BOUNDARY_ARN", "Value": ref("BoundaryArn")}, {"Name": "EXECUTION_ROLE_ARN", "Value": ref("ExecutionRoleArn")}, {"Name": "TASK_ROLE_ARN", "Value": ref("TaskRoleArn")}]
    for name, suffix, buildspec, privileged, service_role in [("Build", "build", "buildspec.yml", True, "BuildRole"), ("Deploy", "deploy", "buildspec-deploy.yml", False, "DeployRole")]:
        r[name] = resource("CodeBuild::Project", Name=sub("${ProjectName}-" + suffix), ServiceRole=att(service_role),
                           Source={"Type": "CODEPIPELINE", "BuildSpec": buildspec}, Artifacts={"Type": "CODEPIPELINE"},
                           Environment={"Type": "LINUX_CONTAINER", "ComputeType": "BUILD_GENERAL1_SMALL", "Image": "aws/codebuild/standard:7.0", "PrivilegedMode": privileged, "EnvironmentVariables": environment},
                           TimeoutInMinutes=30, QueuedTimeoutInMinutes=30,
                           LogsConfig={"CloudWatchLogs": {"Status": "ENABLED", "GroupName": sub("/devsecops/${ProjectName}/" + suffix)}})
    # CodePipeline first checks UseConnection without provider-operation context.
    # Apply contextual restrictions whenever those supported keys are supplied.
    connection_conditions = {"StringEqualsIfExists": {
        "codeconnections:FullRepositoryId": ref("FullRepositoryId"), "codeconnections:BranchName": ref("BranchName")}}
    connection_write_deny = {"Effect": "Deny", "Action": ["codeconnections:UseConnection"], "Resource": ref("ConnectionArn"),
                             "Condition": {"StringLike": {"codeconnections:ProviderAction": ["Create*", "Delete*", "Update*", "GitPush"]}}}
    r["PipelineRole"] = role("codepipeline.amazonaws.com", "pipeline", ref("BoundaryArn"), common + [statement(["codeconnections:UseConnection"], ref("ConnectionArn"), Condition=connection_conditions), connection_write_deny, statement(["codebuild:StartBuild", "codebuild:BatchGetBuilds"], [att("Build"), att("Deploy")])])
    def action(name, provider, category, config, inputs=None, outputs=None):
        a = {"Name": name, "ActionTypeId": {"Category": category, "Owner": "AWS", "Provider": provider, "Version": "1"}, "Configuration": config, "RunOrder": 1}
        if inputs:
            a["InputArtifacts"] = [{"Name": item} for item in inputs]
        if outputs:
            a["OutputArtifacts"] = [{"Name": item} for item in outputs]
        return a
    r["Pipeline"] = resource("CodePipeline::Pipeline", Name=ref("ProjectName"), PipelineType="V2", ExecutionMode="QUEUED", RoleArn=att("PipelineRole"),
                             ArtifactStore={"Type": "S3", "Location": ref("ArtifactBucket")},
                             Stages=[{"Name": "Source", "Actions": [action("GitHub", "CodeStarSourceConnection", "Source", {"ConnectionArn": ref("ConnectionArn"), "FullRepositoryId": ref("FullRepositoryId"), "BranchName": ref("BranchName"), "DetectChanges": "false", "OutputArtifactFormat": "CODE_ZIP"}, outputs=["Source"])]},
                                     {"Name": "BuildScanSign", "Actions": [action("Build", "CodeBuild", "Build", {"ProjectName": ref("Build")}, inputs=["Source"], outputs=["Release"])]},
                                     {"Name": "VerifyDeploy", "Actions": [action("VerifyDeploy", "CodeBuild", "Build", {"ProjectName": ref("Deploy"), "PrimarySource": "Source"}, inputs=["Source", "Release"], outputs=["Deployment"])]}])
    output(t, "PipelineName", ref("Pipeline"))
    return t


def generate_github():
    t = base("GitHub Actions OIDC: separate bounded build and deploy roles; repository IDs and main-only environments control trust.")
    t["Parameters"].update({
        "OidcSubjectPrefix": {"Type": "String", "AllowedPattern": "repo:[^:*?]+", "Description": "Exact subject prefix returned by GitHub OIDC customization API, including immutable IDs when enabled."},
        "ExistingOidcProviderArn": {"Type": "String", "Default": "", "Description": "Reuse an existing GitHub OIDC provider, or leave empty to create one."},
        "RepositoryArn": {"Type": "String"}, "BoundaryArn": {"Type": "String"},
        "ExecutionRoleArn": {"Type": "String"}, "TaskRoleArn": {"Type": "String"},
    })
    t["Conditions"] = {"CreateProvider": {"Fn::Equals": [ref("ExistingOidcProviderArn"), ""]}}
    r = t["Resources"]
    r["Provider"] = resource("IAM::OIDCProvider", Url="https://token.actions.githubusercontent.com", ClientIdList=["sts.amazonaws.com"])
    r["Provider"]["Condition"] = "CreateProvider"
    provider = {"Fn::If": ["CreateProvider", ref("Provider"), ref("ExistingOidcProviderArn")]}
    legacy = generate_pipeline()["Resources"]
    for logical, original, suffix, environment in [("GithubBuildRole", "BuildRole", "github-build", "build"), ("GithubDeployRole", "DeployRole", "github-deploy", "production")]:
        item = copy.deepcopy(legacy[original])
        props = item["Properties"]
        props["RoleName"] = sub("${ProjectName}-" + suffix)
        props["AssumeRolePolicyDocument"] = document([{
            "Effect": "Allow", "Action": ["sts:AssumeRoleWithWebIdentity"], "Principal": {"Federated": provider},
            "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                                           "token.actions.githubusercontent.com:sub": sub("${OidcSubjectPrefix}:environment:" + environment)}}}])
        # GitHub stores its own job logs/artifacts; these roles need no S3/log writes.
        statements = props["Policies"][0]["PolicyDocument"]["Statement"]
        props["Policies"][0]["PolicyDocument"]["Statement"] = [x for x in statements if not any(a.startswith(("s3:", "logs:")) for a in x["Action"])]
        r[logical] = item
        output(t, logical + "Arn", att(logical))
    output(t, "OidcProviderArn", provider)
    return t


def main():
    for name, template in [("platform", generate_platform()), ("runtime", generate_runtime()), ("pipeline", generate_pipeline()), ("github", generate_github())]:
        (HERE / (name + ".json")).write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
