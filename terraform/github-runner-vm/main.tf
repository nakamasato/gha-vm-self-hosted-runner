data "google_project" "current" {}

# Generate startup script
locals {
  # Construct GitHub URL from variables
  github_url = var.github_repo != null ? "https://github.com/${var.github_org}/${var.github_repo}" : "https://github.com/${var.github_org}"

  # Startup script with auto-installation (when token secret is provided)
  startup_script_with_token = <<-EOF
#!/bin/bash
set -e

# Configuration from Terraform variables
PROJECT_ID=$(curl -s "http://metadata.google.internal/computeMetadata/v1/project/project-id" -H "Metadata-Flavor: Google")
TOKEN_SECRET="${var.github_runner_token_secret}"
GITHUB_URL="${local.github_url}"

echo "Configuring GitHub Actions runner for: $GITHUB_URL"

# Install common tools (similar to ubuntu-latest) - only on first boot
if [ ! -f /var/lib/cloud/instance/runner-tools-installed ]; then
  echo "Installing common development tools..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    curl \
    wget \
    unzip \
    jq \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    docker.io \
    docker-compose

  # Create python symlink for compatibility
  ln -sf /usr/bin/python3 /usr/bin/python

  # Clean up apt cache to reduce disk usage
  apt-get clean && rm -rf /var/lib/apt/lists/*

  # Start docker service
  systemctl enable docker
  systemctl start docker

  # Mark as installed
  mkdir -p /var/lib/cloud/instance
  touch /var/lib/cloud/instance/runner-tools-installed
  echo "Tools installation completed"
fi

# Install GitHub Actions runner if not already installed
if [ ! -d "/home/runner/actions-runner" ]; then
  # Create runner user if doesn't exist
  if ! id -u runner > /dev/null 2>&1; then
    useradd -m -s /bin/bash runner
  fi

  # Add runner user to docker group
  usermod -aG docker runner

  # Download and install runner
  cd /home/runner
  mkdir -p actions-runner && cd actions-runner

  # Get latest runner version
  RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep tag_name | cut -d '"' -f 4 | sed 's/v//')
  curl -o actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz -L https://github.com/actions/runner/releases/download/v$${RUNNER_VERSION}/actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz
  tar xzf ./actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz
  rm actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz

  # Get runner token from Secret Manager
  RUNNER_TOKEN=$(gcloud secrets versions access latest --secret="$TOKEN_SECRET" --project="$PROJECT_ID")

  # Configure runner
  chown -R runner:runner /home/runner/actions-runner
  echo "Running config.sh with URL: $GITHUB_URL"
  sudo -u runner ./config.sh --url "$GITHUB_URL" --token "$RUNNER_TOKEN" --unattended --replace

  # Install as service
  ./svc.sh install runner
  ./svc.sh start
else
  # Start existing runner
  cd /home/runner/actions-runner
  ./svc.sh start || true
fi
EOF

  # Simple startup script (when no token secret, assumes manual installation)
  startup_script_without_token = <<-EOF
#!/bin/bash
# Start runner service (assumes runner is already manually installed)
if [ -d "/home/runner/actions-runner" ]; then
  cd /home/runner/actions-runner
  ./svc.sh start || true
fi
EOF

  # Select default startup script based on whether token secret is provided
  default_startup_script = var.github_runner_token_secret != null ? local.startup_script_with_token : local.startup_script_without_token

  # Use custom startup_script if provided, otherwise use default
  final_startup_script = var.startup_script != "" ? var.startup_script : local.default_startup_script
}

# Service Account for GitHub Runner
resource "google_service_account" "runner" {
  project      = data.google_project.current.project_id
  account_id   = var.service_account_id
  display_name = "GitHub Actions Self-Hosted Runner"
  description  = "Service account for GitHub Actions self-hosted runner VM"
}

# IAM roles for the runner service account
resource "google_project_iam_member" "runner_roles" {
  project  = var.project
  for_each = toset(var.roles)
  role     = each.value
  member   = google_service_account.runner.member
}

# Secret Manager access (if GitHub runner token is used)
resource "google_secret_manager_secret_iam_member" "runner_token_access" {
  count     = var.github_runner_token_secret != null ? 1 : 0
  project   = var.project
  secret_id = var.github_runner_token_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runner.member
}

# Compute Instance for GitHub Runner
resource "google_compute_instance" "runner" {
  project      = data.google_project.current.project_id
  name         = var.instance_name
  machine_type = var.machine_type
  zone         = var.zone

  # Scheduling configuration
  scheduling {
    preemptible         = false # Persistent VM
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  # Boot disk
  boot_disk {
    initialize_params {
      image = var.boot_disk_image
      size  = var.boot_disk_size_gb
      type  = var.boot_disk_type
    }
  }

  # Network interface
  network_interface {
    network = var.network
    dynamic "access_config" {
      for_each = var.enable_external_ip ? [1] : []
      content {
        # Ephemeral external IP
      }
    }
  }

  # Startup script
  metadata_startup_script = local.final_startup_script

  # Metadata
  metadata = merge(
    {
      enable-oslogin    = "TRUE"
      runner-configured = "true"
    },
    var.additional_metadata
  )

  # Service account
  service_account {
    email  = google_service_account.runner.email
    scopes = ["cloud-platform"]
  }

  # Labels
  labels = var.labels

  # Lifecycle: ignore desired_status changes (managed by GitHub Actions)
  lifecycle {
    ignore_changes = [
      metadata["desired_status"],
    ]
  }

  tags = var.network_tags
}
