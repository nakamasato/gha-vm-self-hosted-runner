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
  default     = "nakamasato/gha-vm-self-hosted-runner:latest"
}

variable "queue_name" {
  description = "Cloud Tasks queue name"
  type        = string
  default     = "runner-controller"
}

variable "github_webhook_secret" {
  description = "GitHub webhook secret for signature verification"
  type        = string
  sensitive   = true
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
