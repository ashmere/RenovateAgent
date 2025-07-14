# Terraform outputs for RenovateAgent GCP deployment

output "function_name" {
  description = "The name of the deployed Cloud Function"
  value       = google_cloudfunctions2_function.renovate_agent.name
}

output "function_url" {
  description = "The URL of the deployed Cloud Function"
  value       = google_cloudfunctions2_function.renovate_agent.service_config[0].uri
}

output "function_region" {
  description = "The region where the Cloud Function is deployed"
  value       = google_cloudfunctions2_function.renovate_agent.location
}

output "service_account_email" {
  description = "The email of the service account used by the Cloud Function"
  value       = google_service_account.renovate_agent_sa.email
}

output "webhook_secret_id" {
  description = "The secret ID for the GitHub webhook secret"
  value       = google_secret_manager_secret.github_webhook_secret.secret_id
}

output "app_private_key_secret_id" {
  description = "The secret ID for the GitHub App private key"
  value       = google_secret_manager_secret.github_app_private_key.secret_id
}

output "personal_access_token_secret_id" {
  description = "The secret ID for the GitHub Personal Access Token"
  value       = google_secret_manager_secret.github_personal_access_token.secret_id
}

output "deployment_bucket" {
  description = "The Cloud Storage bucket for deployment artifacts"
  value       = google_storage_bucket.deployment_artifacts.name
}

output "monitoring_dashboard_url" {
  description = "URL to the monitoring dashboard"
  value       = "https://console.cloud.google.com/monitoring/dashboards/custom/${google_monitoring_dashboard.renovate_agent_dashboard.id}?project=${var.project_id}"
}

output "function_logs_url" {
  description = "URL to view function logs"
  value       = "https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_function%22%0Aresource.labels.function_name%3D%22${var.function_name}%22?project=${var.project_id}"
}

output "webhook_configuration" {
  description = "GitHub webhook configuration instructions"
  value = {
    url           = google_cloudfunctions2_function.renovate_agent.service_config[0].uri
    content_type  = "application/json"
    secret_source = "Secret Manager: ${google_secret_manager_secret.github_webhook_secret.secret_id}"
    events        = ["pull_request", "check_suite", "issues", "push"]
  }
}

output "setup_instructions" {
  description = "Setup instructions for the deployment"
  value = <<-EOT
    1. Set up secrets in Secret Manager:
       - ${google_secret_manager_secret.github_webhook_secret.secret_id}: Your GitHub webhook secret
       - ${google_secret_manager_secret.github_app_private_key.secret_id}: Your GitHub App private key
       - ${google_secret_manager_secret.github_personal_access_token.secret_id}: Your GitHub PAT (alternative)

    2. Configure GitHub webhook:
       - URL: ${google_cloudfunctions2_function.renovate_agent.service_config[0].uri}
       - Content type: application/json
       - Secret: Use the same value as in Secret Manager
       - Events: pull_request, check_suite, issues, push

    3. Monitor the function:
       - Dashboard: https://console.cloud.google.com/monitoring/dashboards/custom/${google_monitoring_dashboard.renovate_agent_dashboard.id}?project=${var.project_id}
       - Logs: https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_function%22%0Aresource.labels.function_name%3D%22${var.function_name}%22?project=${var.project_id}
  EOT
}
