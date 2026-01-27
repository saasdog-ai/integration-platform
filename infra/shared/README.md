# Shared Infrastructure

This module creates shared AWS infrastructure that can be used by multiple SaaSDog projects:
- Integration Platform
- Import/Export Orchestrator
- Future projects

## Resources Created

- **VPC** with public/private subnets across 2 AZs
- **RDS PostgreSQL** (single instance, multiple databases)
- **ECS Cluster** (shared, each project adds its own service)
- **KMS Key** for credential encryption
- **NAT Gateway** for private subnet internet access

## Usage

### Deploy Shared Infrastructure

```bash
cd infra/shared
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

terraform init
terraform plan
terraform apply
```

### Use in Project

Each project can reference the shared infra by setting:

```hcl
# In project's terraform.tfvars
use_shared_infra = true

# Shared infra outputs (from shared terraform output)
shared_vpc_id              = "vpc-xxx"
shared_private_subnet_ids  = ["subnet-xxx", "subnet-yyy"]
shared_public_subnet_ids   = ["subnet-aaa", "subnet-bbb"]
shared_ecs_cluster_arn     = "arn:aws:ecs:..."
shared_rds_endpoint        = "xxx.rds.amazonaws.com"
shared_kms_key_id          = "xxx-xxx-xxx"
```

### Standalone Deployment

To deploy a project independently (creates its own infra):

```hcl
# In project's terraform.tfvars
use_shared_infra = false
```

## Cost Savings

| Environment | Mode | Estimated Monthly Cost |
|-------------|------|----------------------|
| Dev/Test | Shared | ~$50-80 (single RDS, single NAT) |
| Dev/Test | Standalone x2 | ~$100-160 |
| Production | Standalone | Recommended for isolation |
