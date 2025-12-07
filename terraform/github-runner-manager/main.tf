locals {
  service_name = "github-runner-manager"
  region       = var.region
}

# Data source for project
data "google_project" "current" {
  project_id = var.project
}

# Service Account for Runner Manager (Cloud Run)
resource "google_service_account" "runner_manager" {
  project      = var.project
  account_id   = "runner-manager"
  display_name = "GitHub Runner Manager Service Account"
  description  = "Service account for GitHub Actions runner manager Cloud Run service"
}

# IAM: Compute Instance Admin (to start/stop VM)
resource "google_project_iam_member" "runner_manager_compute" {
  project = var.project
  role    = "roles/compute.instanceAdmin.v1"
  member  = google_service_account.runner_manager.member
}

# IAM: Cloud Tasks Enqueuer (for tasks.create on specific queue)
resource "google_cloud_tasks_queue_iam_member" "runner_manager_tasks_enqueuer" {
  project  = google_cloud_tasks_queue.runner_manager.project
  location = google_cloud_tasks_queue.runner_manager.location
  name     = google_cloud_tasks_queue.runner_manager.name
  role     = "roles/cloudtasks.enqueuer"
  member   = google_service_account.runner_manager.member
}

# IAM: Cloud Tasks Task Deleter (for tasks.delete on specific queue)
resource "google_cloud_tasks_queue_iam_member" "runner_manager_tasks_deleter" {
  project  = google_cloud_tasks_queue.runner_manager.project
  location = google_cloud_tasks_queue.runner_manager.location
  name     = google_cloud_tasks_queue.runner_manager.name
  role     = "roles/cloudtasks.taskDeleter"
  member   = google_service_account.runner_manager.member
}

# Cloud Tasks Queue
resource "google_cloud_tasks_queue" "runner_manager" {
  project  = var.project
  name     = var.queue_name
  location = local.region

  rate_limits {
    max_concurrent_dispatches = 10
    max_dispatches_per_second = 10
  }

  retry_config {
    max_attempts = 3
    max_backoff  = "300s"
    min_backoff  = "60s"
  }
}

# Cloud Run Service
resource "google_cloud_run_v2_service" "runner_manager" {
  project             = var.project
  name                = local.service_name
  location            = local.region
  deletion_protection = var.deletion_protection

  template {
    service_account = google_service_account.runner_manager.email

    containers {
      # Use the Docker image from Docker Hub
      image = var.runner_manager_image

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project
      }

      env {
        name  = "VM_INACTIVE_MINUTES"
        value = var.inactive_minutes
      }

      env {
        name  = "CLOUD_TASK_LOCATION"
        value = local.region
      }

      env {
        name  = "CLOUD_TASK_QUEUE_NAME"
        value = var.queue_name
      }

      env {
        name  = "CLOUD_RUN_SERVICE_URL"
        value = "https://${local.service_name}-${data.google_project.current.number}.${local.region}.run.app"
      }

      env {
        name = "RUNNER_MANAGER_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.runner_manager_secret.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GITHUB_APP_ID"
        value = var.github_app_id
      }

      env {
        name = "GITHUB_APP_PRIVATE_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.github_app_private_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "RUNNER_CONFIG"
        value = var.runner_config
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# Allow unauthenticated access to Cloud Run (for GitHub webhooks)
resource "google_cloud_run_v2_service_iam_member" "runner_manager_invoker" {
  project  = var.project
  location = local.region
  name     = google_cloud_run_v2_service.runner_manager.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Generate random secret for authentication
resource "random_string" "runner_manager_secret" {
  length  = 32
  special = false
}

# Secret Manager: Runner Manager Secret (used for both GitHub webhook and runner control)
resource "google_secret_manager_secret" "runner_manager_secret" {
  project   = var.project
  secret_id = "runner-manager-secret"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "runner_manager_secret_version" {
  secret      = google_secret_manager_secret.runner_manager_secret.id
  secret_data = random_string.runner_manager_secret.result
}

# IAM: Allow Cloud Run to access runner manager secret
resource "google_secret_manager_secret_iam_member" "runner_manager_secret_access" {
  project   = var.project
  secret_id = google_secret_manager_secret.runner_manager_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runner_manager.member
}

# Secret Manager: GitHub App Private Key
# Note: This secret must be created manually before terraform apply
# See README for instructions on creating and uploading the GitHub App private key
data "google_secret_manager_secret" "github_app_private_key" {
  project   = var.project
  secret_id = "github-app-private-key"
}

# IAM: Allow Cloud Run to access GitHub App private key
resource "google_secret_manager_secret_iam_member" "github_app_private_key_access" {
  project   = var.project
  secret_id = data.google_secret_manager_secret.github_app_private_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runner_manager.member
}
