# Terraform variables for RenovateAgent GCP deployment

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "function_name" {
  description = "The name of the Cloud Function"
  type        = string
  default     = "renovate-agent"
}

variable "memory" {
  description = "Memory allocation for the Cloud Function"
  type        = string
  default     = "512Mi"
}

variable "timeout_seconds" {
  description = "Timeout for the Cloud Function in seconds"
  type        = number
  default     = 540
}

variable "min_instances" {
  description = "Minimum number of instances"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 10
}

variable "log_level" {
  description = "Log level for the application"
  type        = string
  default     = "INFO"
  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], var.log_level)
    error_message = "Log level must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL."
  }
}

variable "github_organization" {
  description = "GitHub organization name"
  type        = string
}

variable "github_app_id" {
  description = "GitHub App ID"
  type        = string
  default     = ""
}

variable "enable_dependency_fixing" {
  description = "Enable dependency fixing functionality"
  type        = bool
  default     = true
}

variable "supported_languages" {
  description = "Comma-separated list of supported languages"
  type        = string
  default     = "python,typescript,go"
}

variable "dashboard_creation_mode" {
  description = "Dashboard creation mode (test, any, none, renovate-only)"
  type        = string
  default     = "renovate-only"
  validation {
    condition     = contains(["test", "any", "none", "renovate-only"], var.dashboard_creation_mode)
    error_message = "Dashboard creation mode must be one of test, any, none, renovate-only."
  }
}

variable "renovate_bot_usernames" {
  description = "Comma-separated list of Renovate bot usernames"
  type        = string
  default     = "renovate[bot]"
}

variable "notification_channels" {
  description = "List of notification channels for alerts"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "enable_monitoring" {
  description = "Enable monitoring and alerting"
  type        = bool
  default     = true
}

variable "enable_tracing" {
  description = "Enable distributed tracing"
  type        = bool
  default     = false
}

variable "source_archive_bucket" {
  description = "Bucket to store source archive (if empty, will create one)"
  type        = string
  default     = ""
}

variable "source_archive_object" {
  description = "Object name for source archive"
  type        = string
  default     = "source.zip"
}

variable "environment_variables" {
  description = "Additional environment variables for the function"
  type        = map(string)
  default     = {}
}

variable "secret_environment_variables" {
  description = "Additional secret environment variables for the function"
  type = map(object({
    secret  = string
    version = string
  }))
  default = {}
}
