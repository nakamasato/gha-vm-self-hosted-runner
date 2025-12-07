# GitHub Runner VM Module

This Terraform module creates a persistent Compute Engine VM instance configured as a GitHub Actions self-hosted runner.

> [!IMPORTANT]
> This module only supports **repository-level self-hosted runners**. Organization-level runners are not supported.

## Features

- Creates a persistent VM instance (not preemptible)
- Configures a dedicated service account for the runner
- Supports custom IAM roles for the service account
- Configurable machine type, disk size, and network settings
- Startup script support for runner initialization
- Lifecycle management to ignore `desired_status` metadata changes (managed by GitHub Actions)

## Usage

```hcl
module "github_runner" {
  source = "../../modules/github-runner-vm"

  project       = var.project
  instance_name = "github-runner-persistent"
  machine_type  = "e2-standard-2"  # 2vCPU, 8GB
  zone          = "asia-northeast1-a"

  boot_disk_size_gb = 10

  # GitHub runner configuration
  # When these are provided, the module automatically generates a startup script
  # that installs and configures the runner on first boot
  github_runner_token_secret = "github-runner-token" # Secret Manager secret name
  github_org                 = "your-org"
  github_repo                = "your-repo"           # Required for repository-level runner

  # IAM roles for the runner VM service account
  # Note: This SA is for the VM itself, not for GitHub Actions workflows
  # Workflows should use separate service accounts via Workload Identity Federation
  # Typically no additional roles are needed for the VM
  roles = []

  labels = {
    purpose = "github-runner"
    managed = "terraform"
  }
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| project | GCP project ID where the runner will be created | `string` | n/a | yes |
| instance_name | Name of the Compute Instance | `string` | `"github-runner-persistent"` | no |
| machine_type | Machine type for the runner VM | `string` | `"e2-standard-2"` | no |
| zone | Zone where the VM will be created | `string` | `"asia-northeast1-a"` | no |
| boot_disk_image | Boot disk image for the VM | `string` | `"ubuntu-os-cloud/ubuntu-2204-lts"` | no |
| boot_disk_size_gb | Boot disk size in GB | `number` | `10` | no |
| boot_disk_type | Boot disk type | `string` | `"pd-standard"` | no |
| network | Network to attach the VM to | `string` | `"default"` | no |
| enable_external_ip | Whether to assign an external IP address | `bool` | `true` | no |
| startup_script | Custom startup script (optional, auto-generated if empty) | `string` | `""` | no |
| service_account_id | Service account ID for the runner | `string` | `"github-runner"` | no |
| roles | IAM roles to attach to the runner service account | `list(string)` | `[]` | no |
| additional_metadata | Additional metadata to attach to the VM | `map(string)` | `{}` | no |
| labels | Labels to attach to the VM | `map(string)` | `{}` | no |
| network_tags | Network tags for firewall rules | `list(string)` | `[]` | no |
| github_runner_token_secret | Secret Manager secret name containing the GitHub runner token | `string` | `null` | no |
| github_org | GitHub organization name | `string` | `null` | no |
| github_repo | GitHub repository name | `string` | `null` | no |

## Outputs

| Name | Description |
|------|-------------|
| instance_id | The server-assigned unique identifier of the instance |
| instance_name | The name of the instance |
| instance_self_link | The URI of the instance |
| internal_ip | The internal IP address of the instance |
| external_ip | The external IP address of the instance (if enabled) |
| service_account_email | Email address of the service account used by the runner |
| service_account_member | IAM member format of the service account |
| zone | The zone where the instance is located |

## GitHub Runner Token Setup

> [!IMPORTANT]
> This module only supports **repository-level self-hosted runners**. Organization-level runners are not supported.

To use the GitHub runner token feature, you need to:

1. Generate a runner registration token from GitHub:
   - Go to Repository Settings > Actions > Runners > New self-hosted runner
   - Copy the token from the configuration command

2. Store the token in Secret Manager:
   ```bash
   echo -n "YOUR_RUNNER_TOKEN" | gcloud secrets create github-runner-token \
     --project=YOUR_PROJECT_ID \
     --data-file=-
   ```

3. The module will automatically grant the runner service account access to this secret

Note: GitHub runner tokens expire after some time. You may need to update the secret periodically or implement a token rotation mechanism.

## Notes

- The VM is configured as a persistent (non-preemptible) instance
- The module automatically ignores changes to the `desired_status` metadata field, which can be managed by GitHub Actions workflows
- The service account has OS Login enabled by default for secure SSH access
- When the VM is stopped, you are not charged for compute resources (only storage)
- **Service Account Permissions**:
  - The VM service account is for running the VM itself, not for GitHub Actions workflows
  - Workflows should use separate service accounts via Workload Identity Federation
  - The module automatically grants `roles/secretmanager.secretAccessor` when `github_runner_token_secret` is provided
  - Typically, no additional roles are needed via the `roles` variable
  - Only add roles if the VM itself needs specific permissions (e.g., writing logs to a specific location)
- **Startup Script Behavior**:
  - If `github_runner_token_secret` is provided: Auto-generates script that installs and configures runner on first boot, then starts it on subsequent boots
  - If `github_runner_token_secret` is NOT provided: Simple script that starts pre-installed runner
  - If `startup_script` variable is provided: Uses your custom script instead
- **Runner Scope**:
  - If `github_repo` is **NOT** provided (null): Creates an **organization-wide runner** that can be used by all repositories in the organization
  - If `github_repo` is provided: Creates a **repository-specific runner** that can only be used by that specific repository
- If you provide `github_runner_token_secret`, the module will automatically configure Secret Manager IAM permissions

## Cost Optimization

To minimize costs:
- Stop the VM when not in use (no compute charges, only storage charges)
- Use appropriate machine types based on your workload
- Consider using sustained use discounts for long-running instances

## Limitations

### GitHub Token Management

This module currently uses a static GitHub token stored in Secret Manager, which has the following limitations:

1. **Token Expiration**:
   - **Registration tokens**: Expire after 1 hour (not recommended for persistent runners)
   - **Fine-Grained Personal Access Tokens (PATs)**: Expire after a maximum of 1 year
   - **Classic PATs**: Can be set to never expire, but are less secure

2. **Manual Token Rotation Required**:
   - The token stored in Secret Manager must be manually updated before expiration
   - No automatic token refresh mechanism is currently implemented
   - Expired tokens will prevent new runner registrations (existing runners may continue to work)

3. **Recommended Approach**:
   - Use **Fine-Grained PATs** with the minimum required permissions:
     - Organization-wide runners: `Organization permissions > Self-hosted runners: Read and write`
     - Repository-specific runners: `Repository permissions > Administration: Read and write`
   - Set token expiration to the maximum allowed period (1 year)
   - Implement a process to rotate tokens before expiration

### Future Improvements

For a more robust solution, consider implementing:
- **GitHub App authentication**: Provides better security and automatic token refresh
- **Automated token rotation**: Using Cloud Functions or Cloud Run to periodically refresh tokens
