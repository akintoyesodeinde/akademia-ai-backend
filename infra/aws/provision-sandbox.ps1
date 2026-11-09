<#
.SYNOPSIS
    End-to-End AWS Free-Tier Sandbox Provisioning & Deployment for Akademia AI
    Target AWS Account: 973429899833 (toyesode123@gmail.com)
    AWS CLI Profile:    akademia-deploy
    Default Region:     eu-north-1 (from Console URL ?region=eu-north-1)
    Resources:
      - 1x RDS PostgreSQL 18 (or latest 18.x/17.x/16.x orderable on db.t3.micro), Single-AZ, BackupRetentionPeriod=0 (no backups), 20 GiB Free Tier gp2
      - 1x EC2 t3.micro Instance via Launch Template (AL2023, IMDSv2 required, 20 GiB gp3, no EBS backups)
      - GitHub Actions OIDC Provider + Least-Privilege Role (akademia-github-deploy-role)
      - Automated SSM Parameter Store configuration & initial container deployment
#>
param(
    [string]$Profile = "akademia-deploy",
    [string]$ExpectedAccountId = "973429899833",
    [string]$Region = "eu-north-1",
    [string]$GitHubOwner = "akintoyesodeinde",
    [string]$Ec2InstanceType = "t3.micro",
    [string]$RdsInstanceClass = "db.t3.micro",
    [string]$BackendImageDigest = "akintoyesodeinde/akademia-ai-backend@sha256:e3dfc9f8ea5cd1393276b178a75ed5d1137c3a5d32d7887bea72e048d4b7a8d4",
    [string]$FrontendImageDigest = "akintoyesodeinde/akademia-ai-frontend@sha256:3aff557118edcfe407a284005bce099c1ade960f84b16902d04a194095bbebf3"
)

$ErrorActionPreference = "Continue"

Write-Host "=== [1/9] Verifying AWS STS Identity for profile '$Profile' ==="
$CallerJson = aws sts get-caller-identity --profile $Profile --region $Region --output json | ConvertFrom-Json
$AccountId = $CallerJson.Account
Write-Host "Authenticated Account: $AccountId | ARN: $($CallerJson.Arn)"

if ($AccountId -ne $ExpectedAccountId) {
    throw "SAFETY STOP: Profile '$Profile' authenticated to AWS Account '$AccountId', but expected '$ExpectedAccountId' (toyesode123@gmail.com). Aborting before creating any resources."
}

# Generate strong random passwords for RDS master, runtime roles, and JWT signing
function New-RandomSecret([int]$Length = 28) {
    $chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $bytes) { [void]$sb.Append($chars[$b % $chars.Length]) }
    return $sb.ToString()
}

$RdsMasterPassword = New-RandomSecret 28
$MigratorPassword  = New-RandomSecret 28
$AppPassword       = New-RandomSecret 28
$WorkerPassword    = New-RandomSecret 28
$ReadonlyPassword  = New-RandomSecret 28
$JwtSecretKey      = New-RandomSecret 48

Write-Host "=== [2/9] Configuring GitHub OIDC Provider & Deployment IAM Role ==="
$OidcArn = "arn:aws:iam::${AccountId}:oidc-provider/token.actions.githubusercontent.com"
$ExistingOidc = aws iam list-open-id-connect-providers --profile $Profile --output json | ConvertFrom-Json
if (-not ($ExistingOidc.OpenIDConnectProviderList.Arn -contains $OidcArn)) {
    aws iam create-open-id-connect-provider `
        --profile $Profile `
        --url "https://token.actions.githubusercontent.com" `
        --client-id-list "sts.amazonaws.com" `
        --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" | Out-Null
}

$GithubTrustPolicy = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect = "Allow"
            Principal = @{ Federated = $OidcArn }
            Action = "sts:AssumeRoleWithWebIdentity"
            Condition = @{
                StringEquals = @{ "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
                StringLike = @{
                    "token.actions.githubusercontent.com:sub" = @(
                        "repo:${GitHubOwner}/akademia-ai-backend:*",
                        "repo:${GitHubOwner}/akademia-ai-frontend:*"
                    )
                }
            }
        }
    )
} | ConvertTo-Json -Depth 10 -Compress

$TrustFile = Join-Path $env:TEMP "akademia-github-trust.json"
[System.IO.File]::WriteAllText($TrustFile, $GithubTrustPolicy)
aws iam create-role --profile $Profile --role-name "akademia-github-deploy-role" --assume-role-policy-document "file://$TrustFile" 2>$null | Out-Null
aws iam update-assume-role-policy --profile $Profile --role-name "akademia-github-deploy-role" --policy-document "file://$TrustFile"

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

$DeployPolicyFile = Join-Path $env:TEMP "akademia-github-policy.json"
[System.IO.File]::WriteAllText($DeployPolicyFile, $GithubDeployPolicy)
aws iam put-role-policy --profile $Profile --role-name "akademia-github-deploy-role" --policy-name "AkademiaGitHubSSMDeployPolicy" --policy-document "file://$DeployPolicyFile"

Write-Host "=== [3/9] Configuring EC2 IAM Role & Instance Profile (akademia-ec2-instance-profile) ==="
$Ec2TrustPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
$Ec2TrustFile = Join-Path $env:TEMP "akademia-ec2-trust.json"
[System.IO.File]::WriteAllText($Ec2TrustFile, $Ec2TrustPolicy)

aws iam create-role --profile $Profile --role-name "akademia-ec2-instance-role" --assume-role-policy-document "file://$Ec2TrustFile" 2>$null | Out-Null
aws iam attach-role-policy --profile $Profile --role-name "akademia-ec2-instance-role" --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"

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

$Ec2PolicyFile = Join-Path $env:TEMP "akademia-ec2-policy.json"
[System.IO.File]::WriteAllText($Ec2PolicyFile, $Ec2SsmPolicy)
aws iam put-role-policy --profile $Profile --role-name "akademia-ec2-instance-role" --policy-name "AkademiaEC2ReadRuntimeParameters" --policy-document "file://$Ec2PolicyFile"

aws iam create-instance-profile --profile $Profile --instance-profile-name "akademia-ec2-instance-profile" 2>$null | Out-Null
aws iam add-role-to-instance-profile --profile $Profile --instance-profile-name "akademia-ec2-instance-profile" --role-name "akademia-ec2-instance-role" 2>$null | Out-Null

Write-Host "=== [4/9] Configuring VPC Security Groups (akademia-ec2-sg & akademia-rds-sg) ==="
$VpcId = aws ec2 describe-vpcs --profile $Profile --region $Region --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text
if (-not $VpcId -or $VpcId -eq "None") {
    $VpcId = aws ec2 create-default-vpc --profile $Profile --region $Region --query "Vpc.VpcId" --output text
}

$Ec2SgId = aws ec2 describe-security-groups --profile $Profile --region $Region --filters "Name=group-name,Values=akademia-ec2-sg" "Name=vpc-id,Values=$VpcId" --query "SecurityGroups[0].GroupId" --output text
if (-not $Ec2SgId -or $Ec2SgId -eq "None") {
    $Ec2SgId = aws ec2 create-security-group --profile $Profile --region $Region --group-name "akademia-ec2-sg" --description "Akademia AI EC2 SG - HTTP/HTTPS only" --vpc-id $VpcId --query "GroupId" --output text
    aws ec2 authorize-security-group-ingress --profile $Profile --region $Region --group-id $Ec2SgId --protocol tcp --port 80 --cidr "0.0.0.0/0" | Out-Null
    aws ec2 authorize-security-group-ingress --profile $Profile --region $Region --group-id $Ec2SgId --protocol tcp --port 443 --cidr "0.0.0.0/0" | Out-Null
}

$RdsSgId = aws ec2 describe-security-groups --profile $Profile --region $Region --filters "Name=group-name,Values=akademia-rds-sg" "Name=vpc-id,Values=$VpcId" --query "SecurityGroups[0].GroupId" --output text
if (-not $RdsSgId -or $RdsSgId -eq "None") {
    $RdsSgId = aws ec2 create-security-group --profile $Profile --region $Region --group-name "akademia-rds-sg" --description "Akademia AI RDS SG - 5432 from EC2 SG only" --vpc-id $VpcId --query "GroupId" --output text
    aws ec2 authorize-security-group-ingress --profile $Profile --region $Region --group-id $RdsSgId --protocol tcp --port 5432 --source-group $Ec2SgId | Out-Null
}

Write-Host "=== [5/9] Selecting Free-Tier RDS PostgreSQL Engine Version (preferring 18.x on $RdsInstanceClass) ==="
$OrderableVersions = aws rds describe-orderable-db-instance-options `
    --profile $Profile --region $Region `
    --engine postgres `
    --db-instance-class $RdsInstanceClass `
    --query "OrderableDBInstanceOptions[].EngineVersion" `
    --output json | ConvertFrom-Json | Select-Object -Unique

$SelectedPgVersion = ($OrderableVersions | Where-Object { $_ -like "18.*" } | Sort-Object {[version]($_ -replace '[^0-9.]','')} -Descending | Select-Object -First 1)
if (-not $SelectedPgVersion) {
    $SelectedPgVersion = ($OrderableVersions | Where-Object { $_ -like "17.*" -or $_ -like "16.*" } | Sort-Object {[version]($_ -replace '[^0-9.]','')} -Descending | Select-Object -First 1)
}
Write-Host "Selected RDS PostgreSQL Engine Version for ${RdsInstanceClass}: $SelectedPgVersion"

Write-Host "=== [6/9] Provisioning 1x Free-Tier $RdsInstanceClass RDS PostgreSQL (BackupRetentionPeriod=0, Single-AZ) ==="
$ExistingDbId = aws rds describe-db-instances --profile $Profile --region $Region --query "DBInstances[?DBInstanceIdentifier=='akademia-ai-db'].DBInstanceIdentifier | [0]" --output text
if (-not $ExistingDbId -or $ExistingDbId -eq "None") {
    Write-Host "Creating new RDS instance 'akademia-ai-db' ($RdsInstanceClass, PostgreSQL $SelectedPgVersion, BackupRetentionPeriod=0)..."
    aws rds create-db-instance `
        --profile $Profile --region $Region `
        --db-instance-identifier "akademia-ai-db" `
        --db-instance-class $RdsInstanceClass `
        --engine "postgres" `
        --engine-version $SelectedPgVersion `
        --master-username "postgres" `
        --master-user-password $RdsMasterPassword `
        --db-name "akademia_ai" `
        --allocated-storage 20 `
        --storage-type "gp2" `
        --storage-encrypted `
        --no-multi-az `
        --no-publicly-accessible `
        --backup-retention-period 0 `
        --vpc-security-group-ids $RdsSgId `
        --no-deletion-protection | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create RDS instance akademia-ai-db" }
} else {
    Write-Host "RDS instance 'akademia-ai-db' already exists; ensuring BackupRetentionPeriod=0..."
    aws rds wait db-instance-available --profile $Profile --region $Region --db-instance-identifier "akademia-ai-db"
    aws rds modify-db-instance `
        --profile $Profile --region $Region `
        --db-instance-identifier "akademia-ai-db" `
        --master-user-password $RdsMasterPassword `
        --backup-retention-period 0 `
        --apply-immediately | Out-Null
}

Write-Host "Waiting for RDS instance 'akademia-ai-db' to become available..."
aws rds wait db-instance-available --profile $Profile --region $Region --db-instance-identifier "akademia-ai-db"
$RdsEndpoint = aws rds describe-db-instances --profile $Profile --region $Region --db-instance-identifier "akademia-ai-db" --query "DBInstances[0].Endpoint.Address" --output text
Write-Host "RDS Endpoint Active: $RdsEndpoint"

Write-Host "=== [7/9] Storing Runtime Secrets & Image Digests in AWS SSM Parameter Store ==="
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/rds_endpoint" --type "String" --value $RdsEndpoint --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/rds_master_password" --type "SecureString" --value $RdsMasterPassword --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/migrator_password" --type "SecureString" --value $MigratorPassword --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/app_password" --type "SecureString" --value $AppPassword --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/worker_password" --type "SecureString" --value $WorkerPassword --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/readonly_password" --type "SecureString" --value $ReadonlyPassword --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/database_url" --type "SecureString" --value "postgresql+asyncpg://akademia_app:${AppPassword}@${RdsEndpoint}:5432/akademia_ai" --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/migration_database_url" --type "SecureString" --value "postgresql+asyncpg://akademia_migrator:${MigratorPassword}@${RdsEndpoint}:5432/akademia_ai" --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/worker_database_url" --type "SecureString" --value "postgresql+asyncpg://akademia_worker:${WorkerPassword}@${RdsEndpoint}:5432/akademia_ai" --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/jwt_secret_key" --type "SecureString" --value $JwtSecretKey --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/backend_image" --type "String" --value $BackendImageDigest --overwrite | Out-Null
aws ssm put-parameter --profile $Profile --region $Region --name "/akademia-ai/prod/frontend_image" --type "String" --value $FrontendImageDigest --overwrite | Out-Null

Write-Host "=== [8/9] Creating EC2 Launch Template & Launching 1x Free-Tier $Ec2InstanceType Instance ==="
$AmiId = aws ssm get-parameter --profile $Profile --region $Region --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" --query "Parameter.Value" --output text
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

$LtFile = Join-Path $env:TEMP "akademia-lt-data.json"
[System.IO.File]::WriteAllText($LtFile, $LtData)

aws ec2 delete-launch-template --profile $Profile --region $Region --launch-template-name "akademia-ai-ec2-lt" 2>$null | Out-Null
aws ec2 create-launch-template `
    --profile $Profile --region $Region `
    --launch-template-name "akademia-ai-ec2-lt" `
    --version-description "v1-sandbox-single-ec2-no-backup" `
    --launch-template-data "file://$LtFile" | Out-Null

# Wait 10s for IAM instance profile propagation
Start-Sleep -Seconds 10

$RunningId = aws ec2 describe-instances --profile $Profile --region $Region --filters "Name=tag:Application,Values=akademia-ai" "Name=instance-state-name,Values=pending,running" --query "Reservations[0].Instances[0].InstanceId" --output text
if (-not $RunningId -or $RunningId -eq "None") {
    $InstanceId = aws ec2 run-instances `
        --profile $Profile --region $Region `
        --launch-template LaunchTemplateName=akademia-ai-ec2-lt `
        --count 1 `
        --query "Instances[0].InstanceId" --output text
} else {
    $InstanceId = $RunningId
}

Write-Host "Waiting for EC2 instance $InstanceId to reach running state..."
aws ec2 wait instance-running --profile $Profile --region $Region --instance-ids $InstanceId
$PublicIp = aws ec2 describe-instances --profile $Profile --region $Region --instance-ids $InstanceId --query "Reservations[0].Instances[0].PublicIpAddress" --output text

Write-Host "=== [9/9] Provisioning Complete ==="
Write-Host "  - AWS Account ID:       $AccountId"
Write-Host "  - AWS Region:           $Region"
Write-Host "  - GitHub OIDC Role ARN: arn:aws:iam::${AccountId}:role/akademia-github-deploy-role"
Write-Host "  - RDS Instance:         akademia-ai-db ($RdsInstanceClass, PostgreSQL $SelectedPgVersion, BackupRetentionPeriod=0, Endpoint=$RdsEndpoint)"
Write-Host "  - EC2 Instance:         $InstanceId ($Ec2InstanceType, PublicIP=$PublicIp)"
Write-Host "  - Application URL:      http://$PublicIp"
Write-Host "  - Backend Health URL:   http://$PublicIp/api/v1/platform/health"
