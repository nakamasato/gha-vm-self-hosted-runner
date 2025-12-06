variable "project" {
  description = "GCP project ID"
  type        = string
}

variable "zone" {
  description = "GCP zone for the runner VM"
  type        = string
  default     = "asia-northeast1-a"
}

# GitHub Runner VM Configuration
variable "runner_instance_name" {
  description = "Name of the GitHub runner VM instance"
  type        = string
  default     = "github-runner"
}

variable "runner_machine_type" {
  description = "Machine type for the runner VM"
  type        = string
  default     = "e2-standard-2"
}

variable "runner_disk_size_gb" {
  description = "Boot disk size for the runner VM in GB"
  type        = number
  default     = 20
}

variable "github_runner_token_secret" {
  description = "Secret Manager secret name containing the GitHub runner token"
  type        = string
}

variable "github_org" {
  description = "GitHub organization name"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name (optional, omit for org-wide runner)"
  type        = string
  default     = null
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
