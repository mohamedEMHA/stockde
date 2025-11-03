resource "google_storage_bucket" "raw_landing" {
  name                        = "${var.project_id}-reddit-raw"
  location                    = var.location
  uniform_bucket_level_access = true
  force_destroy               = false
  versioning {
    enabled = true
  }
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 365
    }
  }
}

resource "google_bigquery_dataset" "reddit" {
  dataset_id                  = "reddit_stock_sentiment"
  location                    = var.location
  delete_contents_on_destroy  = false
}

resource "google_secret_manager_secret" "reddit_client_id" {
  secret_id  = "reddit_client_id"
  replication {
    automatic = true
  }
}

resource "google_secret_manager_secret" "reddit_client_secret" {
  secret_id  = "reddit_client_secret"
  replication {
    automatic = true
  }
}

resource "google_secret_manager_secret" "telegram_bot_token" {
  secret_id  = "telegram_bot_token"
  replication {
    automatic = true
  }
}

resource "google_secret_manager_secret" "telegram_chat_id" {
  secret_id  = "telegram_chat_id"
  replication {
    automatic = true
  }
}

resource "google_composer_environment" "airflow" {
  count = var.enable_composer ? 1 : 0
  name  = "reddit-airflow"
  region = var.region

  config {
    software_config {
      image_version = "composer-2.5.5-airflow-2.6.3"
      env_variables = {
        AIRFLOW__CORE__LOAD_EXAMPLES = "False"
      }
    }
  }
}