"""
All-Inkl Einstiegspunkt via Phusion Passenger
Diese Datei muss im Webroot liegen und heißt passenger_wsgi.py
"""

import sys
import os
from pathlib import Path

# Projektverzeichnis zum Pythonpfad hinzufügen
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# .env laden (falls python-dotenv verfügbar)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# FastAPI → ASGI → WSGI Bridge
from asgiref.wsgi import WsgiToAsgi  # noqa: F401 – für WSGI-Hosts
from app.main import app

# Für Passenger: WSGI-Adapter
try:
    from asgiref.sync import AsyncToSync
    # Passenger erwartet 'application'
    from uvicorn.middleware.wsgi import WSGIMiddleware
    application = WSGIMiddleware(app)  # type: ignore
except ImportError:
    # Fallback: direkt ASGI (funktioniert mit uvicorn/gunicorn)
    application = app  # type: ignore
