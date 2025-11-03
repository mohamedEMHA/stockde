variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "location" {
  description = "GCS/BigQuery location"
  type        = string
  default     = "US"
}

variable "enable_composer" {
  description = "Enable Cloud Composer environment creation"
  type        = bool
  default     = false
}