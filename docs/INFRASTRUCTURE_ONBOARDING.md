# Infrastructure Onboarding Guide

This guide covers deploying the Integration Platform to cloud infrastructure. It consolidates deployment steps, security hardening, and production configuration.

## Customer Deployment Checklist

Before deploying, gather the following values:

| Value | Required | Where Used |
|-------|----------|------------|
| AWS region | Yes | All resources |
| Environment name (dev/staging/prod) | Yes | Resource naming |
| Database password | Yes | RDS, ECS task |
| GitHub repository (owner/repo) | Yes | OIDC CI/CD |
| Container image URI | Yes | ECS task definition |
| Deployment mode (standalone/shared) | Yes | Infrastructure topology |
| ACM certificate ARN | No | HTTPS on ALB |
| VPC CIDR | No | Networking (default: 10.1.0.0/16) |

## AWS Deployment

### Architecture

- **ECS Fargate** -- Container orchestration (no servers to manage)
- **RDS PostgreSQL** -- Managed database
- **KMS** -- Encryption keys for integration credentials
- **SQS** -- Message queue for async sync job processing
- **ALB** -- Application Load Balancer (supports HTTPS)
- **Secrets Manager** -- Database credential storage
- **ECR** -- Container image registry

### Step 1: Prerequisites

- AWS CLI installed and configured (`aws configure`)
- Terraform >= 1.0 installed
- Docker installed (for building container images)
- GitHub repository with Actions enabled

### Step 2: Bootstrap State Backend (One Time)

```bash
cd infra/aws/terraform/bootstrap
terraform init
terraform apply
```

This creates the S3 bucket and DynamoDB table for Terraform remote state.

### Step 3: Configure Variables

```bash
cd infra/aws/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values. Key settings:

```hcl
aws_region        = "us-east-1"
environment       = "dev"
app_name          = "integration-platform"
github_repository = "your-org/integration-platform"

# Deployment mode
use_shared_infra = false  # true to use shared VPC/RDS/ECS cluster

# Database
db_instance_class    = "db.t3.micro"   # Production: db.t3.small or larger
db_allocated_storage = 20

# ECS
ecs_task_cpu      = 256    # Production: 512+
ecs_task_memory   = 512    # Production: 1024+
ecs_desired_count = 1      # Production: 2+ for HA
```

### Step 4: Set Database Password

```bash
export TF_VAR_db_password="your-secure-password-here"
```

> **Note**: Terraform uses this variable to create the RDS instance and store credentials
> in AWS Secrets Manager. At runtime, the ECS task pulls credentials from Secrets Manager
> -- the password never appears in the task definition.

### Step 5: Initial Deployment

```bash
terraform init
terraform plan
terraform apply
```

This creates all infrastructure including the GitHub OIDC CI/CD role.

### Step 6: Configure GitHub Secrets

Get the CI/CD role ARN:

```bash
terraform output cicd_role_arn
```

Add secrets to your GitHub repository (Settings > Environments > [env] > Secrets):

- **`AWS_ROLE_ARN`**: The CI/CD role ARN from above
- **`DATABASE_PASSWORD`**: Your database password

### Step 7: Build and Push Docker Image

```bash
# Get ECR repository URL
terraform output ecr_repository_url

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $(terraform output -raw ecr_repository_url | sed 's|https://||')

# Build and push
docker build -t integration-platform:latest .
docker tag integration-platform:latest \
  $(terraform output -raw ecr_repository_url):latest
docker push $(terraform output -raw ecr_repository_url):latest
```

### Step 8: Ongoing Deployments

After initial bootstrap, all deployments go through GitHub Actions:

1. Push to `main` branch to auto-deploy
2. Or manually trigger: Actions > Deploy to AWS > Run workflow

### Verify Deployment

```bash
# Check ECS service status
aws ecs describe-services \
  --cluster integration-platform-dev \
  --services integration-platform-dev-api

# Check health
curl http://$(terraform output -raw alb_dns_name)/health

# Check logs
aws logs tail /ecs/integration-platform-dev --follow
```

## Production vs Dev Configuration

| Setting | Dev Value | Production Recommendation |
|---------|-----------|--------------------------|
| `db_instance_class` | `db.t3.micro` | `db.t3.small` or larger |
| `ecs_task_cpu` | 256 | 512+ |
| `ecs_task_memory` | 512 | 1024+ |
| `ecs_desired_count` | 1 | 2+ for HA |
| `enable_deletion_protection` | false | true |
| Container Insights | enabled | enabled |
| KMS key rotation | enabled | enabled (auto-configured) |

## Deployment Modes

### Standalone Mode (`use_shared_infra = false`)

Creates all infrastructure from scratch:
- VPC with public/private subnets
- RDS PostgreSQL instance
- ECS Fargate cluster
- KMS encryption key
- All security groups

Use this for isolated deployments or when no shared infrastructure exists.

### Shared Mode (`use_shared_infra = true`)

Connects to existing shared infrastructure:
- Uses shared VPC, subnets, and security groups
- Uses shared RDS instance and credentials
- Uses shared ECS cluster
- Uses shared KMS key

Still creates project-specific resources: ECR repository, ECS task definition/service, SQS queues, ALB, CloudWatch logs.

Required variables when `use_shared_infra = true`:

```hcl
shared_vpc_id                    = "vpc-xxx"
shared_public_subnet_ids         = ["subnet-xxx", "subnet-yyy"]
shared_private_subnet_ids        = ["subnet-aaa", "subnet-bbb"]
shared_alb_security_group_id     = "sg-xxx"
shared_ecs_security_group_id     = "sg-yyy"
shared_rds_security_group_id     = "sg-zzz"
shared_ecs_cluster_arn           = "arn:aws:ecs:us-east-1:123456789:cluster/cluster-name"
shared_rds_endpoint              = "db-host.xxx.us-east-1.rds.amazonaws.com:5432"
shared_db_credentials_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789:secret:secret-name"
shared_kms_key_id                = "key-id-here"
```

## Security Hardening Checklist

### Infrastructure

- [ ] **HTTPS** -- Provide ACM certificate ARN to enable HTTPS with automatic HTTP redirect
- [ ] **Enable Container Insights** -- Already enabled by default in `ecs.tf`
- [ ] **Multi-AZ NAT** -- Consider NAT Gateway per AZ for high availability (increases cost)
- [ ] **VPC Flow Logs** -- Enable for network monitoring and security analysis
- [ ] **Secrets Manager** -- Database credentials injected from Secrets Manager at container start (auto-configured)
- [ ] **KMS key rotation** -- Enabled by default for credential encryption keys
- [ ] **Deletion protection** -- Set `enable_deletion_protection = true` for production

### Application

- [ ] **JWT authentication** -- Set `AUTH_ENABLED=true` and configure JWKS URL
- [ ] **Rate limiting** -- Verify limits are appropriate for production traffic

### Database

- [ ] **Instance sizing** -- Right-size for production workload
- [ ] **Encryption at rest** -- Enabled by default (`storage_encrypted = true`)
- [ ] **Automated backups** -- Configure retention period for production
- [ ] **Password rotation** -- Rotate credentials periodically via Secrets Manager

### Monitoring

- [ ] **CloudWatch alarms** -- Set up alerts for ECS task failures, high CPU/memory, SQS queue depth
- [ ] **Health checks** -- ALB health check is auto-configured at `/health`

## Azure Deployment Guidance

The application is cloud-agnostic. AWS-to-Azure service mapping:

| AWS Service | Azure Equivalent | Notes |
|-------------|------------------|-------|
| ECS Fargate | Azure Container Apps / AKS | Container Apps for simpler setup |
| RDS PostgreSQL | Azure Database for PostgreSQL | Flexible Server recommended |
| SQS | Azure Queue Storage | Use `CLOUD_PROVIDER=azure` |
| KMS | Azure Key Vault | Use `CLOUD_PROVIDER=azure` |
| ALB | Azure Application Gateway | Or Azure Front Door |
| Secrets Manager | Azure Key Vault | For database password |
| ECR | Azure Container Registry | For Docker images |
| IAM OIDC | Azure AD Workload Identity | For GitHub Actions CI/CD |
| CloudWatch | Azure Monitor | Logs and metrics |

Key environment variables for Azure:
```bash
CLOUD_PROVIDER=azure
AZURE_STORAGE_ACCOUNT_NAME=<account-name>
```

## GCP Deployment Guidance

AWS-to-GCP service mapping:

| AWS Service | GCP Equivalent | Notes |
|-------------|----------------|-------|
| ECS Fargate | Cloud Run / GKE Autopilot | Cloud Run for simpler setup |
| RDS PostgreSQL | Cloud SQL for PostgreSQL | |
| SQS | Cloud Pub/Sub | Use `CLOUD_PROVIDER=gcp` |
| KMS | Cloud KMS | Use `CLOUD_PROVIDER=gcp` |
| ALB | Cloud Load Balancing | External HTTP(S) LB |
| Secrets Manager | Secret Manager | For database password |
| ECR | Artifact Registry | For Docker images |
| IAM OIDC | Workload Identity Federation | For GitHub Actions CI/CD |
| CloudWatch | Cloud Logging / Monitoring | |

Key environment variables for GCP:
```bash
CLOUD_PROVIDER=gcp
```

## Troubleshooting

### GitHub Actions Fails with "Access Denied"
1. Verify `AWS_ROLE_ARN` secret is correct
2. Check GitHub OIDC provider exists: `aws iam list-open-id-connect-providers`
3. Verify `github_repository` in `terraform.tfvars` matches your repo

### ECS Tasks Not Starting
1. Check CloudWatch Logs for errors
2. Verify container image exists in ECR
3. Check task definition image URI is correct
4. Verify security group allows outbound traffic

### Application Can't Access SQS/KMS
1. Verify ECS task role has correct policies (check `iam.tf`)
2. Check resource ARNs in IAM policies match actual resources

### Database Connection Failed
1. Verify security group allows ECS tasks to access RDS (port 5432)
2. Check database endpoint and credentials are correct
3. Verify RDS is in the same VPC as ECS
