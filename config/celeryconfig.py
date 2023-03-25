broker_url = "mongodb://0.0.0.0:27017/cowbird-jobs"
result_backend = "mongodb://0.0.0.0:27017"
mongodb_backend_settings = {
    "database": "cowbird-jobs",
    "taskmeta_collection": "celery_tasks",
}
result_persistent = False
