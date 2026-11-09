# Akademia AI — AWS IAM & GitHub OIDC Federation Report

## 1. AWS Account Verification Commands (Windows PowerShell)

The target AWS account is associated with `toyesode123@gmail.com` (**AWS Account ID `973429899833`**, region `eu-north-1`). Because an email address is not an AWS account ID or credential, authenticate from Windows PowerShell and verify the actual account ID via AWS STS before provisioning:

```powershell
aws --version

aws configure sso

aws sso login --profile akademia-deploy

aws sts get-caller-identity --profile akademia-deploy
```

### Alternative IAM Authentication Flow (Used for `akademia-deploy` in Account `973429899833`)

When IAM Identity Center (SSO) is not enabled, configure the named CLI profile locally (without pasting access keys into chat or committing them to Git):
```powershell
aws configure --profile akademia-deploy
aws sts get-caller-identity --profile akademia-deploy
```
Verified STS output:
- **Account**: `973429899833`
- **ARN**: `arn:aws:iam::973429899833:user/akademia-deploy`
- **UserId**: `AIDA6F2FCQHA57LJT5V7D`
- **Allowed Region (enforced by AWS Organizations SCP `p-0nel9v63`)**: `eu-north-1`

## 2. GitHub OIDC Identity Provider & Deployment Role (`akademia-github-deploy-role`)

- **Provider URL**: `https://token.actions.githubusercontent.com`
- **Audience (`ClientID`)**: `sts.amazonaws.com`
- **Provisioned IAM Role ARN**: `arn:aws:iam::973429899833:role/akademia-github-deploy-role`
- **AWS Organizations SCP Note (`p-jj3hvbbh`)**: Account `973429899833` belongs to an AWS Organization where SCP `p-jj3hvbbh` restricts `iam:CreateOpenIDConnectProvider` to the management/root administrator while permitting `iam:CreateRole` and `iam:PutRolePolicy`. The role `arn:aws:iam::973429899833:role/akademia-github-deploy-role` is created and configured with the exact OIDC trust policy below; if the OIDC provider resource is not yet registered at the Organization level, register `https://token.actions.githubusercontent.com` (audience `sts.amazonaws.com`) once in the AWS IAM Console -> **Identity providers**.

### Trust Policy (Restricted to Exact Repositories & Protected Branches/Environment)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::973429899833:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:akintoyesodeinde/akademia-ai-backend:ref:refs/heads/main",
            "repo:akintoyesodeinde/akademia-ai-backend:environment:production",
            "repo:akintoyesodeinde/akademia-ai-frontend:ref:refs/heads/main",
            "repo:akintoyesodeinde/akademia-ai-frontend:environment:production"
          ]
        }
      }
    }
  ]
}
```

### Least-Privilege Permissions Policy (`AkademiaGitHubSSMDeployPolicy`)

The GitHub Actions deployment role can only:
1. Update `/akademia-ai/prod/backend_image` and `/akademia-ai/prod/frontend_image` in SSM Parameter Store (`arn:aws:ssm:eu-north-1:973429899833:parameter/akademia-ai/prod/*`).
2. Execute `ssm:SendCommand` (`AWS-RunShellScript`) on the tagged EC2 application instance and inspect command invocation output (`ssm:GetCommandInvocation`, `ec2:DescribeInstances`).

No long-lived `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` credentials are stored in GitHub Actions. Both GitHub repositories are configured with non-secret repository variables:
- `AWS_DEPLOY_ROLE_ARN` = `arn:aws:iam::973429899833:role/akademia-github-deploy-role`
- `AWS_REGION` = `eu-north-1`
- `DOCKERHUB_NAMESPACE` = `akintoyesodeinde`

## 3. EC2 Instance Role & Profile (`akademia-ec2-instance-profile`)

The EC2 application server (`i-0466cd9dca457d16b`) uses its own dedicated IAM role (`arn:aws:iam::973429899833:role/akademia-ec2-instance-role`) via instance profile `arn:aws:iam::973429899833:instance-profile/akademia-ec2-instance-profile`:
- Attached managed policy: `arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore` (enables Systems Manager Session Manager and Run Command without opening SSH port 22).
- Inline least-privilege policy (`AkademiaEC2ReadRuntimeParameters`): grants `ssm:GetParameter`, `ssm:GetParameters`, `ssm:GetParametersByPath` strictly on `arn:aws:ssm:eu-north-1:973429899833:parameter/akademia-ai/prod/*` and `kms:Decrypt` for `SecureString` parameters (`database_url`, `migration_database_url`, `worker_database_url`, `jwt_secret_key`).
