# Web process - Flask keep-alive server
web: gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100 --worker-class sync --worker-connections 1000 --preload keep_alive:app

# Worker process - Main Telegram bot
web: python main.py

# Optional: Release commands (runs before deployment)
release: python -c "import os; print('Environment check:'); print('API_ID:', bool(os.environ.get('API_ID'))); print('DB_URL:', bool(os.environ.get('DB_URL')))"
