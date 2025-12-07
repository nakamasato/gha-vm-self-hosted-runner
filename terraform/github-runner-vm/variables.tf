variable "project" {
  type        = string
  description = "GCP project ID where the runner will be created"
}

variable "instance_name" {
  type        = string
  description = "Name of the Compute Instance"
  default     = "github-runner-persistent"
}

variable "machine_type" {
  type        = string
  description = "Machine type for the runner VM"
  default     = "e2-standard-2" # 2vCPU, 8GB
}

variable "zone" {
  type        = string
  description = "Zone where the VM will be created"
  default     = "asia-northeast1-a"
}

variable "boot_disk_image" {
  type        = string
  description = "Boot disk image for the VM"
  default     = "ubuntu-os-cloud/ubuntu-2204-lts"
}

variable "boot_disk_size_gb" {
  type        = number
  description = "Boot disk size in GB"
  default     = 10
}

variable "boot_disk_type" {
  type        = string
  description = "Boot disk type"
  default     = "pd-standard"
}

variable "network" {
  type        = string
  description = "Network to attach the VM to"
  default     = "default"
}

variable "enable_external_ip" {
  type        = bool
  description = "Whether to assign an external IP address"
  default     = true
}

variable "startup_script" {
  type        = string
  description = "Custom startup script to run when the VM boots. If empty, uses auto-generated script based on github_runner_token_secret configuration."
  default     = ""
}

variable "service_account_id" {
  type        = string
  description = "Service account ID for the runner. Must be 6-30 characters."
  default     = "github-runner"
}

variable "roles" {
  type        = list(string)
  description = "IAM roles to attach to the runner service account"
  default     = []
}

variable "additional_metadata" {
  type        = map(string)
  description = "Additional metadata to attach to the VM"
  default     = {}
}

variable "labels" {
  type        = map(string)
  description = "Labels to attach to the VM"
  default     = {}
}

variable "network_tags" {
  type        = list(string)
  description = "Network tags for firewall rules"
  default     = []
}

variable "github_runner_token_secret" {
  type        = string
  description = "Secret Manager secret name containing the GitHub runner token (e.g., 'github-runner-token'). If provided, the service account needs roles/secretmanager.secretAccessor role."
  default     = null
}

variable "github_org" {
  type        = string
  description = "GitHub organization name (required if github_runner_token_secret is provided)"
  default     = null
}

variable "github_repo" {
  type        = string
  description = "GitHub repository name (required for repository-level runner)"
}
