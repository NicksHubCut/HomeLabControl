"""
Homelab API - All-Inkl Edition
Läuft als FastAPI-App hinter .htaccess Basic Auth
"""

import os
import hashlib
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

from app.auth import verify_token
from app.ratelimit import RateLimiter
from app.registry import ServiceRegistry
from app.executor import Executor
from app.audit import AuditLog

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Homelab API",
    docs_url=None,  # Kein Swagger im Prod
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Singletons ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
registry = ServiceRegistry(BASE_DIR / "services" / "services.yml")
executor = Executor()
audit = AuditLog(BASE_DIR / "logs" / "audit.log")
limiter = RateLimiter(max_requests=30, window=60)

# ── Auth-Dependency ───────────────────────────────────────────────────────────
async def require_auth(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    client_ip = request.client.host

    # Rate limiting
    if not limiter.allow(client_ip):
        audit.log("RATE_LIMIT", client_ip, request.url.path)
        raise HTTPException(status_code=429, detail="Too many requests")

    # Token-Check
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = request.query_params.get("token")

    if not token or not verify_token(token):
        audit.log("AUTH_FAIL", client_ip, request.url.path)
        raise HTTPException(status_code=401, detail="Unauthorized")

    audit.log("AUTH_OK", client_ip, request.url.path)
    return client_ip


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status")
async def get_status(client_ip: str = Depends(require_auth)):
    services = await registry.check_all()
    return {
        "services": services,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/services")
async def list_services(client_ip: str = Depends(require_auth)):
    return {"services": registry.get_all()}


@app.post("/api/wol/{service_name}")
async def wake_on_lan(
    service_name: str,
    client_ip: str = Depends(require_auth),
):
    svc = registry.get(service_name)
    if not svc:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")

    # mac = svc.get("mac")
    mac = os.environ.get("LLM_MAC", "")
    if not mac:
        raise HTTPException(status_code=400, detail="No MAC address configured")

    result = executor.wake_on_lan(mac)
    audit.log("WOL", client_ip, service_name, extra={"mac": mac, "result": result})
    return {"service": service_name, "mac": mac, "result": result}


@app.get("/api/metrics")
async def get_metrics(client_ip: str = Depends(require_auth)):
    """Sammelt GPU/CPU Metriken von Node-Exporter Endpoints"""
    metrics = await registry.fetch_metrics()
    return {"metrics": metrics, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/audit")
async def get_audit(
    limit: int = 50,
    client_ip: str = Depends(require_auth),
):
    entries = audit.get_recent(limit)
    return {"entries": entries, "total": len(entries)}


@app.get("/api/gpu")
async def get_gpu_metrics(client_ip: str = Depends(require_auth)):
    """GPU-Auslastung von nvidia-smi via Node-Exporter"""
    gpu_data = await registry.fetch_gpu_metrics()
    return {"gpu": gpu_data, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Static UI ─────────────────────────────────────────────────────────────────
ui_path = BASE_DIR / "ui"
if ui_path.exists():
    app.mount("/", StaticFiles(directory=str(ui_path), html=True), name="ui")
