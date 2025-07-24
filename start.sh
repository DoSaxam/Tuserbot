#!/bin/bash

echo "🚀 Starting Telegram Auto-Forwarder..."
echo "📅 Start time: $(date)"
echo "🌍 Environment: ${RENDER_SERVICE_NAME:-Local}"

# Set environment variables for optimal performance
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONIOENCODING=utf-8

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "❌ Error: main.py not found!"
    exit 1
fi

echo "✅ All checks passed. Starting application..."

# Start the application
python main.py
