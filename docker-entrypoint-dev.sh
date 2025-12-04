#!/bin/bash
set -e

echo "============================================"
echo "  Document Q&A - Development Mode"
echo "============================================"

# Start backend with hot reload
echo "Starting Backend (port 8000)..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &

# Start frontend dev server
echo "Starting Frontend (port 3000)..."
cd /app/frontend && npm run dev -- --host 0.0.0.0 &

echo ""
echo "============================================"
echo "  Servers Started!"
echo "============================================"
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "============================================"

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?

