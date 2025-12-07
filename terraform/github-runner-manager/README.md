# GitHub Runner Manager Terraform Module

This Terraform module deploys the GitHub Runner Manager infrastructure on GCP. It manages the lifecycle of an **existing** GitHub Actions self-hosted runner VM.

## What This Deploys

1. **Runner Manager Service**: A Cloud Run service that receives GitHub webhooks and manages VM lifecycle
2. **Cloud Tasks Queue**: For scheduling automatic VM shutdown after inactivity
3. **Service Accounts**: With appropriate IAM permissions to start/stop the VM
4. **Secret Manager**: For storing runner manager authentication secret

## Prerequisites

### 1. Existing GitHub Runner VM

This module assumes you already have a GitHub Actions self-hosted runner VM running in GCP. The VM should be:
- Running in the same GCP project
- Configured with a GitHub Actions runner
- Named (default: `github-runner`) - configure via `runner_instance_name` variable

Refer to `../github-runner-vm/` module for creating the VM if you don't have one yet.

### 2. GCP APIs Enabled

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudtasks.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable compute.googleapis.com
```

### 3. Terraform

Terraform >= 1.5.0

### 4. GitHub App Configuration

The runner manager requires a GitHub App to check running workflow jobs before stopping the VM.

**Create GitHub App:**

1. Go to your GitHub organization/user Settings > Developer settings > GitHub Apps > New GitHub App
2. Configure the app:
   - **Name**: `GitHub Runner Manager` (or any name you prefer)
   - **Homepage URL**: Your Cloud Run URL (can be updated later)
   - **Webhook**: Uncheck "Active" (we use webhook separately)
   - **Repository permissions**:
     - Administration: Read-only (to check self-hosted runner status)
   - **Where can this GitHub App be installed?**: Only on this account
3. Create the app and note down:
   - **App ID**: Found on the app settings page
   - **Private Key**: Generate and download from the app settings page
4. Install the app:
   - Go to "Install App" in the left sidebar
   - Install on your organization/user account
   - Select repositories (or all repositories)
   - Note down the **Installation ID** from the URL: `https://github.com/settings/installations/{installation_id}`

**Important Notes:**

- **Repository-level runners only**: This runner manager is designed for **repository-level self-hosted runners**. It checks the busy status of a specific runner registered to a repository. For **organization-level self-hosted runners**, the GitHub API may not return accurate runner status, as the runner could be assigned to jobs from different repositories within the organization.
- If you need to manage organization-level runners, you may need to modify the implementation to check organization runners instead of repository runners.

**Prepare credentials:**

```bash
# Save the private key
cat > github-app-private-key.pem
# Paste the private key content and press Ctrl+D

# Store in Secret Manager (will be automated by Terraform later)
gcloud secrets create github-app-private-key --data-file=github-app-private-key.pem
```

## Setup Instructions

### 1. Configure Terraform Variables

```bash
# Copy the example file
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values
vim terraform.tfvars
```

**Required variables:**
```hcl
project                = "your-gcp-project-id"
zone                   = "asia-northeast1-a"  # Zone where your VM is located
runner_instance_name   = "github-runner"      # Name of your existing VM

# GitHub App configuration
github_app_id          = "123456"             # Your GitHub App ID
github_app_installation_id = "12345678"       # Installation ID from GitHub
github_repo            = "owner/repo"         # Repository to monitor (format: owner/repo)
```

**Optional variables:**
```hcl
region               = "asia-northeast1"      # Region for Cloud Run
runner_manager_image = "docker.io/nakamasato/gha-vm-self-hosted-runner:latest"
queue_name           = "runner-manager"
inactive_minutes     = "15"                   # VM auto-stop timeout
target_labels        = "self-hosted"          # Job label filtering
deletion_protection  = true                   # Prevent accidental deletion
```

### 2. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the configuration
terraform apply
```

### 3. Configure GitHub Webhook

After deployment, configure the webhook in GitHub:

```bash
# Get the webhook URL from Terraform output
terraform output webhook_url

# Get the runner manager secret from Secret Manager
export PROJECT_ID="your-gcp-project-id"
gcloud secrets versions access latest --secret=runner-manager-secret --project=$PROJECT_ID
```

**GitHub Webhook Configuration:**

1. Go to your organization or repository Settings > Webhooks
2. Click "Add webhook"
3. Configure:
   - **Payload URL**: Output from `terraform output webhook_url`
   - **Content type**: `application/json`
   - **Secret**: Output from the `gcloud secrets versions access` command above
   - **Events**: Select "Workflow jobs"
   - **Active**: ✓ Checked
4. Click "Add webhook"

### 4. Test the Setup

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
4. VM stops after configured inactivity period

## Configuration Options

### Target Labels

Filter which jobs trigger VM startup by configuring `target_labels`:

```hcl
# In terraform.tfvars
target_labels = "self-hosted,linux"  # Only jobs with both labels
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

### Custom Docker Image

Use your own fork or version:

```hcl
# In terraform.tfvars
runner_manager_image = "docker.io/your-dockerhub/your-image:v1.0.0"
```

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
gcloud tasks queues describe runner-manager \
  --project=$PROJECT_ID \
  --location=asia-northeast1
```

## Outputs

- `runner_manager_url`: URL of the Cloud Run service
- `runner_manager_service_account`: Email of the service account
- `cloud_tasks_queue_name`: Name of the Cloud Tasks queue
- `webhook_url`: GitHub webhook URL (use this in GitHub settings)
- `runner_manager_secret_id`: Secret Manager secret ID for runner manager authentication

## Troubleshooting

### Webhook not working

Check Cloud Run logs:
```bash
gcloud run services logs read github-runner-manager --region=asia-northeast1
```

Common issues:
- Invalid signature → Verify the secret in GitHub webhook matches Secret Manager (use `gcloud secrets versions access latest --secret=runner-manager-secret`)
- Missing permissions → Verify service account has `roles/compute.instanceAdmin.v1`
- Wrong VM name → Check `runner_instance_name` matches your actual VM name

### VM not starting

1. Check if target labels match:
```bash
curl https://your-service-url.run.app/
# Check "target_labels" in response
```

2. Verify the job labels in your workflow include all target labels

3. Check Cloud Run logs for error messages

### VM not stopping

Check Cloud Tasks queue:
```bash
gcloud tasks list --queue=runner-manager --location=asia-northeast1
```

If tasks are stuck, check:
- Service account has proper permissions
- VM name is correct
- Cloud Tasks queue is healthy

## Cost Estimation

This module's resources cost (excluding the VM itself):

- **Cloud Run**: ~$0.00 (free tier, minimal usage)
- **Cloud Tasks**: ~$0.00 (free tier)
- **Secret Manager**: ~$0.06/secret/month

**Total**: ~$0.06/month

VM costs are separate and depend on your machine type and usage.

## Cleanup

To destroy all resources created by this module:

**If deletion_protection is enabled (default):**
```bash
# First, disable deletion protection
# Set deletion_protection = false in terraform.tfvars
terraform apply

# Then destroy
terraform destroy
```

**If deletion_protection is disabled:**
```bash
terraform destroy
```

**Note**: This will delete:
- Cloud Run service
- Cloud Tasks queue
- Service accounts
- Runner manager secret

It will **NOT** delete your runner VM (as it's not managed by this module).

## Module Usage

To use this as a Terraform module:

```hcl
module "github_runner_manager" {
  source = "github.com/nakamasato/gha-vm-self-hosted-runner//terraform/github-runner-manager"

  project              = "your-gcp-project-id"
  zone                 = "asia-northeast1-a"
  runner_instance_name = "github-runner"

  # Optional
  region              = "asia-northeast1"
  inactive_minutes    = "15"
  target_labels       = "self-hosted,linux"
  deletion_protection = true
}

output "webhook_url" {
  value = module.github_runner_manager.webhook_url
}

output "runner_manager_secret_id" {
  value = module.github_runner_manager.runner_manager_secret_id
}
```

## References

- [GitHub Actions Self-Hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [GitHub Webhooks](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- [GCP Cloud Run](https://cloud.google.com/run/docs)
- [GCP Cloud Tasks](https://cloud.google.com/tasks/docs)
