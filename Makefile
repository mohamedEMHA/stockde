SHELL := /bin/bash

.PHONY: up down airflow-init logs terraform-init terraform-plan terraform-apply terraform-destroy pre-commit-install

up:
	docker compose up -d

airflow-init:
	docker compose up airflow-init

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200 webserver

terraform-init:
	cd terraform && terraform init

terraform-plan:
	cd terraform && terraform plan

terraform-apply:
	cd terraform && terraform apply -auto-approve

terraform-destroy:
	cd terraform && terraform destroy -auto-approve

pre-commit-install:
	pre-commit install