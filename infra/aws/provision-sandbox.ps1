<#
.SYNOPSIS
    Provisions the cost-optimized Akademia AI AWS Sandbox Infrastructure:
    - GitHub Actions OIDC Provider & Least-Privilege Deployment IAM Role
    - EC2 Instance Profile (SSM Session Manager + Parameter Store read access)
    - Security Groups (EC2: 80/443 only; RDS: 5432 from EC2 SG only; no SSH/5432/6379 public exposure)
    - 1x Amazon RDS PostgreSQL 16 (db.t3.micro, Single-AZ, BackupRetentionPeriod=0 / no backups)
    - 1x Amazon EC2 Launch Template & Single Instance (t3.micro, AL2023, IMDSv2 required, encrypted gp3)
#>
param(
    [string]$Profile = "akademia-deploy",
    [string]$Region = "us-east-1",
    [string]$GitHubOwner = "akintoyesodeinde",
    [string]$Ec2InstanceType = "t3.micro",
    [string]$RdsInstanceClass = "db.t3.micro",
    [Parameter(Mandatory = $true)]
    [string]$RdsMasterPassword
)

$ErrorActionPreference = "Stop"

Write-Host "1. Verifying AWS STS Caller Identity..."
$CallerJson = aws sts get-caller-identity --profile $Profile --region $Region --output json | ConvertFrom-Json
$AccountId = $CallerJson.Account
Write-Host "Authenticated AWS Account: $AccountId ($($CallerJson.Arn))"

Write-Host "2. Ensuring GitHub OIDC Provider exists..."
$OidcArn = "arn:aws:iam::${AccountId}:oidc-provider/token.actions.githubusercontent.com"
$ExistingOidc = aws iam list-open-id-connect-providers --profile $Profile --output json | ConvertFrom-Json
if (-not ($ExistingOidc.OpenIDConnectProviderList.Arn -contains $OidcArn)) {
    aws iam create-open-id-connect-provider `
        --profile $Profile `
        --url "https://token.actions.githubusercontent.com" `
        --client-id-list "sts.amazonaws.com" `
        --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" | Out-Null
}

Write-Host "3. Creating GitHub OIDC Deployment Role (akademia-github-deploy-role)..."
$GithubTrustPolicy = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect = "Allow"
            Principal = @{ Federated = $OidcArn }
            Action = "sts:AssumeRoleWithWebIdentity"
            Condition = @{
                StringEquals = @{
                    "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
                }
                StringLike = @{
                    "token.actions.githubusercontent.com:sub" = @(
                        "repo:${GitHubOwner}/akademia-ai-backend:ref:refs/heads/main",
                        "repo:${GitHubOwner}/akademia-ai-backend:environment:production",
                        "repo:${GitHubOwner}/akademia-ai-frontend:ref:refs/heads/main",
                        "repo:${GitHubOwner}/akademia-ai-frontend:environment:production"
                    )
                }
            }
        }
    )
} | ConvertTo-Json -Depth 10 -Compress

aws iam create-role `
    --profile $Profile `
    --role-name "akademia-github-deploy-role" `
    --assume-role-policy-document $GithubTrustPolicy 2>$null | Out-Null

$GithubDeployPolicy = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Sid = "UpdateApprovedImageDigests"
            Effect = "Allow"
            Action = @("ssm:PutParameter", "ssm:GetParameter")
            Resource = @(
                "arn:aws:ssm:${Region}:${AccountId}:parameter/akademia-ai/prod/backend_image",
                "arn:aws:ssm:${Region}:${AccountId}:parameter/akademia-ai/prod/frontend_image"
            )
        },
        @{
            Sid = "TriggerSSMRunCommandOnTaggedEC2"
            Effect = "Allow"
            Action = @("ssm:SendCommand")
            Resource = @(
                "arn:aws:ssm:${Region}::document/AWS-RunShellScript",
                "arn:aws:ec2:${Region}:${AccountId}:instance/*"
            )
        },
        @{
            Sid = "InspectSSMCommandStatusAndTargetInstance"
            Effect = "Allow"
            Action = @("ssm:GetCommandInvocation", "ssm:ListCommandInvocations", "ec2:DescribeInstances")
            Resource = "*"
        }
    )
} | ConvertTo-Json -Depth 10 -Compress

aws iam put-role-policy `
    --profile $Profile `
    --role-name "akademia-github-deploy-role" `
    --policy-name "AkademiaGitHubSSMDeployPolicy" `
    --policy-document $GithubDeployPolicy

Write-Host "4. Creating EC2 IAM Role & Instance Profile (akademia-ec2-instance-profile)..."
$Ec2TrustPolicy = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect = "Allow"
            Principal = @{ Service = "ec2.amazonaws.com" }
            Action = "sts:AssumeRole"
        }
    )
} | ConvertTo-Json -Depth 10 -Compress

aws iam create-role `
    --profile $Profile `
    --role-name "akademia-ec2-instance-role" `
    --assume-role-policy-document $Ec2TrustPolicy 2>$null | Out-Null

aws iam attach-role-policy `
    --profile $Profile `
    --role-name "akademia-ec2-instance-role" `
    --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"

$Ec2SsmPolicy = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect = "Allow"
            Action = @("ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath")
            Resource = "arn:aws:ssm:${Region}:${AccountId}:parameter/akademia-ai/prod/*"
        },
        @{
            Effect = "Allow"
            Action = @("kms:Decrypt")
            Resource = "*"
        }
    )
} | ConvertTo-Json -Depth 10 -Compress

aws iam put-role-policy `
    --profile $Profile `
    --role-name "akademia-ec2-instance-role" `
    --policy-name "AkademiaEC2ReadRuntimeParameters" `
    --policy-document $Ec2SsmPolicy

aws iam create-instance-profile `
    --profile $Profile `
    --instance-profile-name "akademia-ec2-instance-profile" 2>$null | Out-Null

aws iam add-role-to-instance-profile `
    --profile $Profile `
    --instance-profile-name "akademia-ec2-instance-profile" `
    --role-name "akademia-ec2-instance-role" 2>$null | Out-Null

Write-Host "5. Configuring VPC Security Groups (akademia-ec2-sg & akademia-rds-sg)..."
$VpcId = aws ec2 describe-vpcs --profile $Profile --region $Region --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text

$Ec2SgId = aws ec2 create-security-group `
    --profile $Profile --region $Region `
    --group-name "akademia-ec2-sg" `
    --description "Akademia AI EC2 Security Group - HTTP/HTTPS only (no SSH/DB)" `
    --vpc-id $VpcId --query "GroupId" --output text

aws ec2 authorize-security-group-ingress --profile $Profile --region $Region --group-id $Ec2SgId --protocol tcp --port 80 --cidr "0.0.0.0/0" | Out-Null
aws ec2 authorize-security-group-ingress --profile $Profile --region $Region --group-id $Ec2SgId --protocol tcp --port 443 --cidr "0.0.0.0/0" | Out-Null

$RdsSgId = aws ec2 create-security-group `
    --profile $Profile --region $Region `
    --group-name "akademia-rds-sg" `
    --description "Akademia AI RDS PostgreSQL Security Group - 5432 from EC2 SG only" `
    --vpc-id $VpcId --query "GroupId" --output text

aws ec2 authorize-security-group-ingress `
    --profile $Profile --region $Region `
    --group-id $RdsSgId `
    --protocol tcp --port 5432 `
    --source-group $Ec2SgId | Out-Null

Write-Host "6. Creating RDS PostgreSQL 16 ($RdsInstanceClass) with NO BACKUPS (--backup-retention-period 0) for sandbox economy..."
aws rds create-db-instance `
    --profile $Profile --region $Region `
    --db-instance-identifier "akademia-ai-db" `
    --db-instance-class $RdsInstanceClass `
    --engine "postgres" `
    --engine-version "16.4" `
    --master-username "postgres" `
    --master-user-password $RdsMasterPassword `
    --db-name "akademia_ai" `
    --allocated-storage 20 `
    --storage-type "gp3" `
    --storage-encrypted `
    --no-multi-az `
    --no-publicly-accessible `
    --backup-retention-period 0 `
    --vpc-security-group-ids $RdsSgId `
    --no-deletion-protection | Out-Null

Write-Host "7. Creating EC2 Launch Template (akademia-ai-ec2-lt) and launching 1x $Ec2InstanceType instance..."
$AmiId = aws ssm get-parameter `
    --profile $Profile --region $Region `
    --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" `
    --query "Parameter.Value" --output text

$UserDataBytes = [System.IO.File]::ReadAllBytes("$PSScriptRoot\user-data.sh")
$UserDataBase64 = [System.Convert]::ToBase64String($UserDataBytes)

$LtData = @{
    ImageId = $AmiId
    InstanceType = $Ec2InstanceType
    IamInstanceProfile = @{ Name = "akademia-ec2-instance-profile" }
    SecurityGroupIds = @($Ec2SgId)
    UserData = $UserDataBase64
    MetadataOptions = @{
        HttpTokens = "required"
        HttpPutResponseHopLimit = 2
        HttpEndpoint = "enabled"
    }
    BlockDeviceMappings = @(
        @{
            DeviceName = "/dev/xvda"
            Ebs = @{
                VolumeSize = 20
                VolumeType = "gp3"
                Encrypted = $true
                DeleteOnTermination = $true
            }
        }
    )
    TagSpecifications = @(
        @{
            ResourceType = "instance"
            Tags = @(
                @{ Key = "Name"; Value = "akademia-ai-app-1" },
                @{ Key = "Application"; Value = "akademia-ai" },
                @{ Key = "Environment"; Value = "sandbox" }
            )
        }
    )
} | ConvertTo-Json -Depth 10 -Compress

aws ec2 create-launch-template `
    --profile $Profile --region $Region `
    --launch-template-name "akademia-ai-ec2-lt" `
    --version-description "v1-sandbox-single-ec2-no-backup" `
    --launch-template-data $LtData | Out-Null

$InstanceId = aws ec2 run-instances `
    --profile $Profile --region $Region `
    --launch-template "LaunchTemplateName=akademia-ai-ec2-lt,Version=1" `
    --min-count 1 --max-count 1 `
    --query "Instances[0].InstanceId" --output text

Write-Host "Provisioning initiated:"
Write-Host "  - GitHub OIDC Role ARN: arn:aws:iam::${AccountId}:role/akademia-github-deploy-role"
Write-Host "  - RDS Instance: akademia-ai-db ($RdsInstanceClass, BackupRetentionPeriod=0)"
Write-Host "  - EC2 Instance ID: $InstanceId ($Ec2InstanceType)"
