from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.sensors.external_task import ExternalTaskSensor


with DAG(
    dag_id="dag_dbt_run_and_test",
    default_args={"owner": "airflow"},
    schedule_interval="@hourly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["dbt", "transformation"],
) as dag:
    wait_for_ingest = ExternalTaskSensor(
        task_id="wait_for_ingest",
        external_dag_id="dag_ingest_reddit",
        external_task_id="load_gcs_to_bq",
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        poke_interval=300,
        timeout=3600,
        mode="reschedule",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            "dbt build --profiles-dir /opt/airflow/dbt --project-dir /opt/airflow/transform"
        ),
        env={
            "DBT_PROFILES_DIR": "/opt/airflow/dbt",
            "DBT_PROJECT_DIR": "/opt/airflow/transform",
        },
    )

    wait_for_ingest >> dbt_build