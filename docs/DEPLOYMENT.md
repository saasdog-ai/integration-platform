# Deployment Guide

This guide covers deploying the Integration Platform to a customer environment.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Shared Infrastructure                            │
│  (deployed once, shared by multiple applications)                    │
│                                                                      │
│   ┌─────────┐    ┌─────────────┐    ┌─────────────────┐            │
│   │   VPC   │    │ ECS Cluster │    │ RDS PostgreSQL  │            │
│   │ Subnets │    │  (Fargate)  │    │   (Shared DB)   │            │
│   │   NAT   │    │             │    │                 │            │
│   └─────────┘    └─────────────┘    └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Integration Platform                               │
│  (application-specific resources)                                    │
│                                                                      │
│   ┌─────────┐    ┌─────────────┐    ┌───────┐    ┌───────────────┐ │
│   │   ALB   │───▶│ ECS Service │───▶│  SQS  │    │ Secrets/KMS   │ │
│   │         │    │   (Tasks)   │    │ Queue │    │               │ │
│   └─────────┘    └─────────────┘    └───────┘    └───────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform >= 1.5.0
- Docker (for building images locally, if needed)
- PostgreSQL client (psql) for database initialization

## Deployment Steps

### Step 1: Deploy Shared Infrastructure (One-time)

The shared infrastructure (VPC, ECS Cluster, RDS) is deployed once and shared by all applications.

```bash
cd /path/to/shared-infrastructure/infra/aws/terraform

# 1. Bootstrap Terraform state (first time only)
cd bootstrap
terraform init
terraform apply
cd ..

# 2. Deploy shared infrastructure
terraform init
terraform apply
```

**Outputs to note:**
- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`
- `ecs_cluster_arn`
- `ecs_cluster_name`
- `rds_endpoint`
- `rds_address`
- `rds_security_group_id`
- `rds_master_password_secret_arn`

### Step 2: Initialize Application Database

A DBA must create the application database and user on the shared RDS instance.

```bash
# Get RDS master password
aws secretsmanager get-secret-value \
  --secret-id "saasdog-shared-rds-master-password-dev" \
  --query 'SecretString' --output text

# Connect and run initialization script
# (requires network access to RDS - use bastion or VPN)
psql -h <rds-endpoint> -U postgres -f scripts/init-database.sql
```

**Alternative for development:** Use the postgres master user directly (the app's start.sh will create the database automatically).

### Step 3: Deploy Application Infrastructure

```bash
cd /path/to/integration-platform/infra/aws/terraform

# 1. Create terraform.tfvars with shared infrastructure values
# See terraform.tfvars.example for template

# 2. Initialize and apply
terraform init \
  -backend-config="bucket=<state-bucket>" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=<lock-table>"

terraform apply
```

**Outputs to note:**
- `alb_dns_name` - Application URL
- `ecr_repository_url` - Docker image repository
- `ecs_service_name` - ECS service name

### Step 4: Create Admin API Key

The admin API (`/admin/*` endpoints) requires an API key stored in Secrets Manager. This key is **not** managed by Terraform — you create it once per environment.

```bash
# Generate and store the key
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw admin_api_key_secret_arn)" \
  --secret-string "$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"

# Retrieve it (you'll need this for the admin-host-app config)
aws secretsmanager get-secret-value \
  --secret-id "$(terraform output -raw admin_api_key_secret_arn)" \
  --query 'SecretString' --output text
```

Configure the **admin-host-app** with the same key value:
- Set `ADMIN_API_KEY` environment variable, or
- Update `vite.config.ts` → `ADMIN_API_KEY` constant (development only)

The ECS task definition already references this secret — it will be injected as the `ADMIN_API_KEY` environment variable at container startup.

### Step 5: Build and Deploy Application

For CI/CD (recommended), push to main branch. The GitHub Actions workflow will:
1. Build Docker image
2. Push to ECR
3. Update ECS service

For manual deployment:
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build --platform linux/amd64 -t <ecr-url>:latest .
docker push <ecr-url>:latest

# Force new deployment
aws ecs update-service \
  --cluster <cluster-name> \
  --service <service-name> \
  --force-new-deployment
```

### Step 6: Verify Deployment

```bash
# Check health
curl http://<alb-dns>/health

# Check available integrations
curl http://<alb-dns>/integrations/available
```

## CI/CD Setup

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `AWS_ROLE_ARN` | IAM role ARN for GitHub OIDC |
| `TERRAFORM_TFVARS` | Contents of terraform.tfvars |

### Workflow Files

- `.github/workflows/build-and-push-image.yml` - Build and deploy Docker images
- `.github/workflows/deploy.yml` - Terraform infrastructure changes
- `.github/workflows/ci.yml` - Tests and linting

## Configuration Reference

### terraform.tfvars

```hcl
# General
company_prefix = "your-company"
environment    = "dev"         # dev, staging, prod
aws_region     = "us-east-1"
app_name       = "integration-platform"

# Shared Infrastructure (from shared-infrastructure outputs)
shared_vpc_id                         = "vpc-xxx"
shared_public_subnet_ids              = ["subnet-xxx", "subnet-yyy"]
shared_private_subnet_ids             = ["subnet-aaa", "subnet-bbb"]
shared_ecs_cluster_arn                = "arn:aws:ecs:..."
shared_ecs_cluster_name               = "your-company-shared-ecs-dev"
shared_rds_endpoint                   = "xxx.rds.amazonaws.com:5432"
shared_rds_address                    = "xxx.rds.amazonaws.com"
shared_rds_security_group_id          = "sg-xxx"
shared_rds_master_password_secret_arn = "arn:aws:secretsmanager:..."

# Application
db_name         = "integration_platform"
db_username     = "integration_platform"
ecs_task_cpu    = 256
ecs_task_memory = 512
container_port  = 8000

# CI/CD
github_repository = "your-org/integration-platform"
```

## Secrets & Credentials Inventory

All secrets used by the platform, where they live, and how they flow into the running application.

### Storage Locations

| Secret | Storage | How It Gets There | Accessed By |
|--------|---------|-------------------|-------------|
| **Database URL** | AWS Secrets Manager | Terraform generates password, builds connection string, stores in Secrets Manager | ECS injects as `DATABASE_URL` env var at container startup |
| **Admin API Key** | AWS Secrets Manager | Created manually once per environment (see Step 4) | ECS injects as `ADMIN_API_KEY` env var; checked by `app/auth/admin.py` |
| **OAuth client credentials** (client_id, client_secret per integration) | Database (`available_integrations.connection_config` JSONB) | Seed migration inserts; admin updates via API | `integration_service.py` reads at OAuth connect/callback time |
| **OAuth tokens** (access_token, refresh_token per user) | Database (`user_integrations.credentials_encrypted`) | Encrypted with KMS after OAuth callback; re-encrypted on token refresh | `sync_orchestrator.py` decrypts at sync time |
| **KMS encryption key** | AWS KMS | Terraform creates with automatic rotation enabled | App references via `KMS_KEY_ID` env var; encrypts/decrypts OAuth tokens |
| **JWT signing key** | Environment variable (`JWT_SECRET_KEY`) | Set in deployment config; must be changed from default in production | `app/auth/jwt.py` signs/verifies tokens |
| **RDS master password** | AWS Secrets Manager (shared-infrastructure) | Terraform generates in shared-infrastructure stack | Used only for DBA tasks (init-database.sql); app uses its own DB user |
| **SQS queue URL** | ECS env var (`QUEUE_URL`) | Terraform outputs queue URL, set in task definition | `app/infrastructure/queue/` sends/receives sync job messages |
| **KMS Key ID** | ECS env var (`KMS_KEY_ID`) | Terraform outputs key ID, set in task definition | `app/infrastructure/encryption/aws_kms.py` |
| **AWS credentials** | IAM task role (production) / env vars (development) | ECS Fargate assigns task role automatically; local dev uses `.env` | boto3 SDK for KMS, SQS, Secrets Manager |

### How Secrets Flow (Production)

```
Terraform apply
  ├── Creates KMS key → KMS_KEY_ID → ECS task env var
  ├── Creates SQS queue → QUEUE_URL → ECS task env var
  ├── Generates DB password → DATABASE_URL → Secrets Manager → ECS task secret
  └── Creates admin key shell → (manual: put-secret-value) → Secrets Manager → ECS task secret

ECS Task Startup
  ├── Execution role reads Secrets Manager → injects DATABASE_URL, ADMIN_API_KEY as env vars
  └── Task role grants access to KMS, SQS, CloudWatch at runtime

OAuth Flow
  ├── Client credentials read from DB (available_integrations.connection_config)
  ├── User authorizes → tokens received → encrypted with KMS → stored in DB
  └── Sync job decrypts tokens with KMS → calls external API
```

### Development vs Production

| Secret | Development | Production |
|--------|-------------|------------|
| Database URL | `.env` file (`postgres:postgres@localhost:5433`) | Secrets Manager → ECS injection |
| Admin API Key | Optional (access allowed without it) | Required (Secrets Manager → ECS) |
| OAuth tokens | Encrypted with local Fernet (derived from JWT secret) | Encrypted with AWS KMS |
| JWT signing key | Default `CHANGE_THIS_IN_PRODUCTION` | Must be a strong random key |
| AWS credentials | `.env` or `~/.aws/credentials` | IAM task role (no keys needed) |

### Security Notes

- **No secrets in the Docker image** — all injected at runtime via Secrets Manager or env vars
- **OAuth client credentials are in the database**, not env vars — this allows per-integration configuration without redeployment, but means the seed migration contains development credentials that should be rotated for production
- **KMS key rotation** is enabled by default in Terraform
- **OAuth state tokens** (CSRF protection) are stored in-memory — lost on restart, not shared across replicas

## Troubleshooting

### ECS Tasks Failing

1. Check CloudWatch logs:
   ```bash
   aws logs get-log-events \
     --log-group-name "/ecs/saasdog-integration-platform-dev" \
     --log-stream-name "api/integration-platform-api/<task-id>"
   ```

2. Common issues:
   - **Database connection failed**: Check security group rules, DATABASE_URL secret
   - **Migration failed**: Check migration compatibility with schema
   - **Container exits immediately**: Check start.sh script

### Health Check Failing

1. Verify target group health:
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn <target-group-arn>
   ```

2. Check security group allows port 8000 from ALB

### Database Issues

1. Verify RDS is accessible:
   ```bash
   # From within VPC (bastion/VPN)
   psql -h <rds-endpoint> -U postgres -c "SELECT 1"
   ```

2. Check DATABASE_URL secret is correct:
   ```bash
   aws secretsmanager get-secret-value \
     --secret-id "saasdog-integration-platform-database-url-dev"
   ```

## Resource Naming Convention

All resources follow the pattern: `{company}-{project}-{purpose}-{env}`

Examples:
- `saasdog-integration-platform-alb-dev`
- `saasdog-integration-platform-ecs-sg-dev`
- `saasdog-shared-ecs-dev`

## Cleanup

To destroy resources:

```bash
# 1. Destroy application resources first
cd integration-platform/infra/aws/terraform
terraform destroy

# 2. Then destroy shared infrastructure (if no other apps using it)
cd shared-infrastructure/infra/aws/terraform
terraform destroy
```

**Warning:** Destroying shared infrastructure will affect all applications using it.
