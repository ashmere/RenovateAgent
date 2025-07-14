# Terraform configuration for RenovateAgent Google Cloud Functions deployment
# This creates the necessary infrastructure for running RenovateAgent in GCP

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Provider configuration
provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "cloudfunctions_api" {
  service = "cloudfunctions.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild_api" {
  service = "cloudbuild.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

resource "google_project_service" "logging_api" {
  service = "logging.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

resource "google_project_service" "monitoring_api" {
  service = "monitoring.googleapis.com"
  project = var.project_id

  disable_on_destroy = false
}

# Service account for Cloud Function
resource "google_service_account" "renovate_agent_sa" {
  account_id   = "renovate-agent"
  display_name = "RenovateAgent Service Account"
  description  = "Service account for RenovateAgent Cloud Function"
  project      = var.project_id
}

# IAM bindings for service account
resource "google_project_iam_member" "renovate_agent_logs_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.renovate_agent_sa.email}"
}

resource "google_project_iam_member" "renovate_agent_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.renovate_agent_sa.email}"
}

resource "google_project_iam_member" "renovate_agent_trace_writer" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.renovate_agent_sa.email}"
}

# Secret Manager secret for GitHub webhook secret
resource "google_secret_manager_secret" "github_webhook_secret" {
  secret_id = "github-webhook-secret"
  project   = var.project_id

  replication {
    automatic = true
  }
}

# Secret Manager secret for GitHub App private key
resource "google_secret_manager_secret" "github_app_private_key" {
  secret_id = "github-app-private-key"
  project   = var.project_id

  replication {
    automatic = true
  }
}

# Secret Manager secret for GitHub Personal Access Token (alternative)
resource "google_secret_manager_secret" "github_personal_access_token" {
  secret_id = "github-personal-access-token"
  project   = var.project_id

  replication {
    automatic = true
  }
}

# IAM binding for service account to access secrets
resource "google_secret_manager_secret_iam_member" "webhook_secret_access" {
  secret_id = google_secret_manager_secret.github_webhook_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.renovate_agent_sa.email}"
  project   = var.project_id
}

resource "google_secret_manager_secret_iam_member" "app_private_key_access" {
  secret_id = google_secret_manager_secret.github_app_private_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.renovate_agent_sa.email}"
  project   = var.project_id
}

resource "google_secret_manager_secret_iam_member" "pat_access" {
  secret_id = google_secret_manager_secret.github_personal_access_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.renovate_agent_sa.email}"
  project   = var.project_id
}

# Cloud Storage bucket for deployment artifacts
resource "google_storage_bucket" "deployment_artifacts" {
  name          = "${var.project_id}-renovate-agent-artifacts"
  location      = var.region
  force_destroy = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

# Cloud Function (Gen 2)
resource "google_cloudfunctions2_function" "renovate_agent" {
  name        = var.function_name
  location    = var.region
  description = "RenovateAgent webhook processor"
  project     = var.project_id

  build_config {
    runtime     = "python311"
    entry_point = "renovate_webhook"
    source {
      storage_source {
        bucket = google_storage_bucket.deployment_artifacts.name
        object = "source.zip"
      }
    }
  }

  service_config {
    max_instance_count = var.max_instances
    min_instance_count = var.min_instances
    available_memory   = var.memory
    timeout_seconds    = var.timeout_seconds

    environment_variables = {
      DEPLOYMENT_MODE     = "serverless"
      LOG_LEVEL          = var.log_level
      LOG_FORMAT         = "json"
      GITHUB_ORGANIZATION = var.github_organization
      GITHUB_APP_ID      = var.github_app_id
      GITHUB_API_URL     = "https://api.github.com"
      ENABLE_DEPENDENCY_FIXING = var.enable_dependency_fixing
      SUPPORTED_LANGUAGES = var.supported_languages
      DASHBOARD_CREATION_MODE = var.dashboard_creation_mode
      RENOVATE_BOT_USERNAMES = var.renovate_bot_usernames
    }

    secret_environment_variables {
      key        = "GITHUB_WEBHOOK_SECRET"
      project_id = var.project_id
      secret     = google_secret_manager_secret.github_webhook_secret.secret_id
      version    = "latest"
    }

    secret_environment_variables {
      key        = "GITHUB_APP_PRIVATE_KEY"
      project_id = var.project_id
      secret     = google_secret_manager_secret.github_app_private_key.secret_id
      version    = "latest"
    }

    ingress                       = "ALLOW_ALL"
    all_traffic_on_latest_revision = true
    service_account_email         = google_service_account.renovate_agent_sa.email
  }

  depends_on = [
    google_project_service.cloudfunctions_api,
    google_project_service.cloudbuild_api,
  ]
}

# Cloud Function IAM to allow unauthenticated invocations
resource "google_cloudfunctions2_function_iam_member" "invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.renovate_agent.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# Log-based metrics for monitoring
resource "google_logging_metric" "webhook_requests" {
  name   = "renovate_agent_webhook_requests"
  filter = "resource.type=cloud_function AND resource.labels.function_name=${var.function_name}"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    display_name = "Webhook Requests"
  }

  project = var.project_id
}

resource "google_logging_metric" "webhook_errors" {
  name   = "renovate_agent_webhook_errors"
  filter = "resource.type=cloud_function AND resource.labels.function_name=${var.function_name} AND severity>=ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    display_name = "Webhook Errors"
  }

  project = var.project_id
}

# Monitoring alert policy for function errors
resource "google_monitoring_alert_policy" "function_errors" {
  display_name = "RenovateAgent Function Errors"
  combiner     = "OR"
  enabled      = true
  project      = var.project_id

  conditions {
    display_name = "Function error rate"

    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/renovate_agent_webhook_errors\" AND resource.type=\"cloud_function\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.notification_channels

  depends_on = [
    google_project_service.monitoring_api,
    google_logging_metric.webhook_errors,
  ]
}

# Monitoring dashboard
resource "google_monitoring_dashboard" "renovate_agent_dashboard" {
  dashboard_json = jsonencode({
    displayName = "RenovateAgent Monitoring"
    mosaicLayout = {
      tiles = [
        {
          width = 6
          height = 4
          widget = {
            title = "Function Invocations"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"cloudfunctions.googleapis.com/function/executions\" AND resource.type=\"cloud_function\" AND resource.labels.function_name=\"${var.function_name}\""
                      aggregation = {
                        alignmentPeriod = "300s"
                        perSeriesAligner = "ALIGN_RATE"
                      }
                    }
                  }
                }
              ]
            }
          }
        },
        {
          width = 6
          height = 4
          widget = {
            title = "Function Duration"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"cloudfunctions.googleapis.com/function/execution_times\" AND resource.type=\"cloud_function\" AND resource.labels.function_name=\"${var.function_name}\""
                      aggregation = {
                        alignmentPeriod = "300s"
                        perSeriesAligner = "ALIGN_MEAN"
                      }
                    }
                  }
                }
              ]
            }
          }
        }
      ]
    }
  })

  project = var.project_id

  depends_on = [
    google_project_service.monitoring_api,
  ]
}
