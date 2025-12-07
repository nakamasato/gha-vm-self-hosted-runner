variable "project" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run and Cloud Tasks"
  type        = string
  default     = "asia-northeast1"
}

variable "zone" {
  description = "GCP zone where the runner VM is located"
  type        = string
  default     = "asia-northeast1-a"
}

# Existing Runner VM Configuration
variable "runner_instance_name" {
  description = "Name of the existing GitHub runner VM instance"
  type        = string
  default     = "github-runner"
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

variable "target_labels" {
  description = "Comma-separated list of labels to target (e.g., 'self-hosted,linux')"
  type        = string
  default     = "self-hosted"
}

variable "deletion_protection" {
  description = "Enable deletion protection for Cloud Run service"
  type        = bool
  default     = true
}

# GitHub App Configuration
variable "github_app_id" {
  description = "GitHub App ID for querying workflow runs"
  type        = string
}

variable "github_app_installation_id" {
  description = "GitHub App Installation ID"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository to monitor (format: owner/repo)"
  type        = string
}
