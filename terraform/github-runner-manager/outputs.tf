output "runner_manager_url" {
  description = "URL of the GitHub Runner Manager service"
  value       = google_cloud_run_v2_service.runner_manager.uri
}

output "runner_manager_service_account" {
  description = "Email of the runner manager service account"
  value       = google_service_account.runner_manager.email
}

output "cloud_tasks_queue_name" {
  description = "Name of the Cloud Tasks queue"
  value       = google_cloud_tasks_queue.runner_manager.name
}

output "webhook_url" {
  description = "GitHub webhook URL (configure this in GitHub)"
  value       = "${google_cloud_run_v2_service.runner_manager.uri}/github/webhook"
}

output "webhook_secret_id" {
  description = "Secret Manager secret ID for GitHub webhook secret"
  value       = google_secret_manager_secret.webhook_secret.secret_id
}
