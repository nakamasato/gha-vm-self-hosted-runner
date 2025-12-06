# GitHub Runner Infrastructure Example

This directory contains a complete example of deploying the GitHub Actions self-hosted runner infrastructure on GCP.

## What This Deploys

1. **GitHub Runner VM**: A Compute Engine VM that runs the GitHub Actions self-hosted runner
2. **Runner Manager Service**: A Cloud Run service that manages VM lifecycle
3. **Cloud Tasks Queue**: For scheduling automatic VM shutdown
4. **Service Accounts**: With appropriate IAM permissions
5. **Secret Manager**: For storing GitHub webhook secret

## Prerequisites

1. **GCP Project** with billing enabled
2. **APIs enabled**:
   ```bash
   gcloud services enable compute.googleapis.com
   gcloud services enable run.googleapis.com
   gcloud services enable cloudtasks.googleapis.com
   gcloud services enable secretmanager.googleapis.com
   ```
3. **GitHub runner token** stored in Secret Manager
4. **GitHub webhook secret** (generate a random string)
5. **Terraform** installed (>= 1.5.0)

## Setup Instructions

### 1. Create GitHub Runner Token

```bash
# For organization-wide runner:
# Go to: https://github.com/organizations/YOUR_ORG/settings/actions/runners/new

# For repository-specific runner:
# Go to: https://github.com/YOUR_ORG/YOUR_REPO/settings/actions/runners/new

# Copy the token from the configuration command
```

### 2. Store Token in Secret Manager

```bash
export PROJECT_ID="your-gcp-project-id"
export RUNNER_TOKEN="YOUR_GITHUB_RUNNER_TOKEN"

echo -n "$RUNNER_TOKEN" | gcloud secrets create github-runner-token \
  --project=$PROJECT_ID \
  --data-file=-
```

### 3. Generate Webhook Secret

```bash
# Generate a random secret
export WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "GitHub Webhook Secret: $WEBHOOK_SECRET"
# Save this for later!
```

### 4. Configure Terraform Variables

```bash
# Copy the example file
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values
vim terraform.tfvars
```

**Required variables:**
```hcl
project                    = "your-gcp-project-id"
zone                       = "asia-northeast1-a"
github_org                 = "your-github-org"
github_runner_token_secret = "github-runner-token"  # Secret Manager name
github_webhook_secret      = "paste-your-webhook-secret-here"
```

### 5. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the configuration
terraform apply
```

### 6. Configure GitHub Webhook

After deployment, configure the webhook in GitHub:

```bash
# Get the webhook URL from Terraform output
terraform output webhook_url
```

**GitHub Webhook Configuration:**

1. Go to your organization or repository Settings > Webhooks
2. Click "Add webhook"
3. Configure:
   - **Payload URL**: `<webhook_url from terraform output>`
   - **Content type**: `application/json`
   - **Secret**: `<your-webhook-secret>`
   - **Events**: Select "Workflow jobs"
   - **Active**: ✓ Checked
4. Click "Add webhook"

### 7. Test the Setup

Create a workflow that uses the self-hosted runner:

```yaml
# .github/workflows/test.yml
name: Test Self-Hosted Runner

on: [push]

jobs:
  test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - run: echo "Running on self-hosted runner!"
      - run: uname -a
```

Push this workflow and verify:
1. Webhook is received (check Cloud Run logs)
2. VM starts automatically
3. Workflow executes successfully
4. VM stops after 15 minutes of inactivity

## Monitoring

### Cloud Run Logs

```bash
gcloud run services logs read github-runner-manager \
  --project=$PROJECT_ID \
  --region=asia-northeast1 \
  --limit=50
```

### VM Status

```bash
gcloud compute instances describe github-runner \
  --project=$PROJECT_ID \
  --zone=asia-northeast1-a \
  --format="get(status)"
```

### Cloud Tasks Queue

```bash
gcloud tasks queues describe runner-controller \
  --project=$PROJECT_ID \
  --location=asia-northeast1
```

## Configuration Options

### Target Labels

Filter which jobs trigger VM startup by configuring `target_labels`:

```hcl
# In terraform.tfvars
target_labels = "self-hosted,linux"  # Only Linux jobs
```

Corresponding workflow:
```yaml
jobs:
  build:
    runs-on: [self-hosted, linux]
```

### Inactivity Timeout

Adjust how long the VM stays running after the last job:

```hcl
# In terraform.tfvars
inactive_minutes = "30"  # Wait 30 minutes before stopping
```

### VM Size

Adjust VM resources based on your workload:

```hcl
# In terraform.tfvars
runner_machine_type = "e2-standard-4"  # 4 vCPU, 16GB RAM
runner_disk_size_gb = 50               # 50GB disk
```

## Cost Estimation

Approximate monthly costs (asia-northeast1):

- **VM (e2-standard-2)**: ~$0.067/hour × hours_running
- **Cloud Run**: ~$0.00 (free tier, minimal usage)
- **Cloud Tasks**: ~$0.00 (free tier)
- **Secret Manager**: ~$0.06/secret/month
- **Network egress**: Varies by usage

**Example**: If VM runs 8 hours/day, 22 days/month:
- VM cost: $0.067 × 8 × 22 = ~$11.79/month
- Other services: ~$0.10/month
- **Total**: ~$12/month

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Note**: This will delete:
- Runner VM
- Cloud Run service
- Cloud Tasks queue
- Service accounts
- Webhook secret (NOT the runner token secret)

## Troubleshooting

### Webhook not working

Check Cloud Run logs:
```bash
gcloud run services logs read github-runner-manager --region=asia-northeast1
```

Common issues:
- Invalid webhook signature → Check `GITHUB_WEBHOOK_SECRET` matches
- Missing permissions → Verify service account IAM roles

### VM not starting

Check if target labels match:
```bash
curl https://your-service-url.run.app/
# Check "target_labels" in response
```

### VM not stopping

Check Cloud Tasks queue:
```bash
gcloud tasks queues list --location=asia-northeast1
gcloud tasks list --queue=runner-controller --location=asia-northeast1
```

## Advanced Configuration

### Multiple Runners

Deploy multiple instances for different purposes:

```hcl
# runner-linux.tf
module "runner_linux" {
  source = "../github-runner-vm"
  instance_name = "github-runner-linux"
  # ... other config
}

# runner-gpu.tf
module "runner_gpu" {
  source = "../github-runner-vm"
  instance_name = "github-runner-gpu"
  machine_type  = "n1-standard-4"
  # Add GPU configuration
}
```

### Custom Runner Labels

Configure the runner with custom labels in the VM startup script:

```hcl
# In variables.tf, add additional_metadata
additional_metadata = {
  runner-labels = "linux,docker,gpu"
}
```

## References

- [GitHub Actions Self-Hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [GitHub Webhooks](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- [GCP Cloud Run](https://cloud.google.com/run/docs)
- [GCP Cloud Tasks](https://cloud.google.com/tasks/docs)
