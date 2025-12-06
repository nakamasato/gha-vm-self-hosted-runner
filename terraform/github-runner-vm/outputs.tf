output "instance_id" {
  description = "The server-assigned unique identifier of the instance"
  value       = google_compute_instance.runner.instance_id
}

output "instance_name" {
  description = "The name of the instance"
  value       = google_compute_instance.runner.name
}

output "instance_self_link" {
  description = "The URI of the instance"
  value       = google_compute_instance.runner.self_link
}

output "internal_ip" {
  description = "The internal IP address of the instance"
  value       = google_compute_instance.runner.network_interface[0].network_ip
}

output "external_ip" {
  description = "The external IP address of the instance (if enabled)"
  value       = var.enable_external_ip ? google_compute_instance.runner.network_interface[0].access_config[0].nat_ip : null
}

output "service_account_email" {
  description = "Email address of the service account used by the runner"
  value       = google_service_account.runner.email
}

output "service_account_member" {
  description = "IAM member format of the service account"
  value       = google_service_account.runner.member
}

output "zone" {
  description = "The zone where the instance is located"
  value       = google_compute_instance.runner.zone
}
