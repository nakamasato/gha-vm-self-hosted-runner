variable "project" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run and Cloud Tasks"
  type        = string
  default     = "asia-northeast1"
}

# Runner Manager Configuration
variable "runner_manager_image" {
  description = "Docker image for the runner manager"
  type        = string
  default     = "docker.io/nakamasato/gha-vm-self-hosted-runner:latest"
}

variable "queue_name" {
  description = "Cloud Tasks queue name"
  type        = string
  default     = "runner-manager"
}

variable "inactive_minutes" {
  description = "Minutes of inactivity before stopping the VM"
  type        = string
  default     = "15"
}

variable "deletion_protection" {
  description = "Enable deletion protection for Cloud Run service"
  type        = bool
  default     = true
}

# GitHub App Configuration
variable "github_app_id" {
  description = "GitHub App ID for authentication"
  type        = string
}

variable "github_installation_id" {
  description = "GitHub App Installation ID (same for all repositories)"
  type        = string
}

# Runner Configuration
variable "runner_config" {
  description = "JSON array of runner configurations. Each entry contains: repo, labels, vm_instance_name, vm_instance_zone"
  type        = string
  # Example: '[{"repo": "owner/repo1", "labels": ["self-hosted"], "vm_instance_name": "github-runner-1", "vm_instance_zone": "asia-northeast1-a"}]'
}
