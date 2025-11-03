output "bucket_name" {
  value = google_storage_bucket.raw_landing.name
}

output "dataset_id" {
  value = google_bigquery_dataset.reddit.dataset_id
}