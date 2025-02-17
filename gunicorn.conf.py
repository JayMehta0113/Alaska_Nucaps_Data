bind = "127.0.0.1:8000"
workers = 4
worker_class = "gthread"
threads = 4
timeout = 300
preload_app = True

#gunicorn FlaskApp:app -c gunicorn.conf.py