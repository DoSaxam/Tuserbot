web: gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 60 keep_alive:app
worker: python main.py
