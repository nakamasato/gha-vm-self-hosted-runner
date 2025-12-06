output "runner_vm_name" {
  description = "Name of the GitHub runner VM"
  value       = module.github_runner_vm.instance_name
}

output "runner_vm_zone" {
  description = "Zone of the GitHub runner VM"
  value       = module.github_runner_vm.zone
}

output "runner_vm_internal_ip" {
  description = "Internal IP of the GitHub runner VM"
  value       = module.github_runner_vm.internal_ip
}

output "runner_vm_external_ip" {
  description = "External IP of the GitHub runner VM"
  value       = module.github_runner_vm.external_ip
}

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
  value       = google_cloud_tasks_queue.runner_controller.name
}

output "webhook_url" {
  description = "GitHub webhook URL (configure this in GitHub)"
  value       = "${google_cloud_run_v2_service.runner_manager.uri}/github/webhook"
}
