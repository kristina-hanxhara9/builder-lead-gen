#!/bin/bash
set -e

echo "=== Smith & Sons Lead Generation System Setup ==="

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required. Install from https://docker.com"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3.11+ is required."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Node.js 20+ is required."; exit 1; }

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it with your API keys."
fi

# Start infrastructure
echo "Starting PostgreSQL and Redis..."
docker compose up -d postgres redis
sleep 3

# Backend setup
echo "Setting up backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
cd ..

# Frontend setup
echo "Setting up frontend..."
cd frontend
npm install
cd ..

echo ""
echo "=== Setup Complete ==="
echo "Start backend:  cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
echo "Start frontend: cd frontend && npm run dev"
echo "Start Celery:   cd backend && celery -A app.tasks worker -l info"
echo "Or use Docker:  docker compose up"
