broker_url = "mongodb://0.0.0.0:27017/jobs"
result_backend = 'mongodb://0.0.0.0:27017'
mongodb_backend_settings = {
    'database': 'jobs-result',
    'taskmeta_collection': 'celery_tasks',
}
result_persistent = False
