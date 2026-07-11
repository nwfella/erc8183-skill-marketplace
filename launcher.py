"""Launcher: fixes PYTHONPATH pollution, then starts the server."""
import sys
# Strip Hermes agent venv from path (broken pydantic_core for this Python)
sys.path = [p for p in sys.path if 'hermes-agent' not in p]

from src.server import app, PORT
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=PORT)
