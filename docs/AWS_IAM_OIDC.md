# Akademia AI — AWS IAM & GitHub OIDC Federation Report

## 1. AWS Account Verification Commands (Windows PowerShell)

The target AWS account is associated with `toyesode123@gmail.com`. Because an email address is not an AWS account ID or credential, authenticate from Windows PowerShell and verify the actual account ID via AWS STS before provisioning:

```powershell
aws --version

aws configure sso

aws sso login --profile akademia-deploy

aws sts get-caller-identity --profile akademia-deploy
```

### Alternative IAM Authentication Flow (When IAM Identity Center / SSO Is Not Configured)

If the sandbox AWS account uses standard IAM users rather than IAM Identity Center (SSO):
1. Sign in to the AWS Management Console (`toyesode123@gmail.com`) -> **IAM** -> **Users** -> create/select an administrative user with MFA enabled.
2. Create a short-lived CLI access key locally and configure the named profile in PowerShell (never paste access keys into chat or commit them to Git):
   ```powershell
   aws configure --profile akademia-deploy
   aws sts get-caller-identity --profile akademia-deploy
   ```

## 2. GitHub OIDC Identity Provider Configuration

- **Provider URL**: `https://token.actions.githubusercontent.com`
- **Audience (`ClientID`)**: `sts.amazonaws.com`
- **IAM Role Name**: `akademia-github-deploy-role`

### Trust Policy (Restricted to Exact Repositories & Protected Branches/Environment)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
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
1. Update `/akademia-ai/prod/backend_image` and `/akademia-ai/prod/frontend_image` in SSM Parameter Store.
2. Execute `ssm:SendCommand` (`AWS-RunShellScript`) on the tagged EC2 application instance and inspect command invocation output (`ssm:GetCommandInvocation`, `ec2:DescribeInstances`).

No long-lived `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` credentials are stored in GitHub Actions.

## 3. EC2 Instance Role & Profile (`akademia-ec2-instance-profile`)

The EC2 application server uses its own dedicated IAM role (`akademia-ec2-instance-role`):
- Attached managed policy: `arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore` (enables Systems Manager Session Manager and Run Command without opening SSH port 22).
- Inline least-privilege policy (`AkademiaEC2ReadRuntimeParameters`): grants `ssm:GetParameter`, `ssm:GetParameters`, `ssm:GetParametersByPath` strictly on `arn:aws:ssm:<REGION>:<ACCOUNT_ID>:parameter/akademia-ai/prod/*` and `kms:Decrypt` for `SecureString` parameters (`database_url`, `migration_database_url`, `worker_database_url`, `jwt_secret_key`).
