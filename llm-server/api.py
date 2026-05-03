#!/usr/bin/env python3
"""LLM Server Control API – start/stop local services via REST"""

from flask import Flask, jsonify, request
from pathlib import Path
from datetime import datetime
import subprocess, requests, json, os, threading, hmac, logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app   = Flask(__name__)
BASE  = Path(__file__).parent
TOKEN = os.environ.get('LOCAL_API_TOKEN', '')

# ── Config ─────────────────────────────────────────────────────────────────────

def load_services() -> dict:
    with open(BASE / 'services.json') as f:
        return json.load(f)

def auth_ok() -> bool:
    if not TOKEN:
        return True
    return hmac.compare_digest(TOKEN, request.headers.get('X-Api-Token', ''))

# ── Status checks ──────────────────────────────────────────────────────────────

def check_http(url: str) -> bool:
    try:
        r = requests.get(url, timeout=5)
        return r.status_code < 500
    except Exception:
        return False

def check_docker(container: str) -> bool:
    try:
        r = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}'],
            capture_output=True, text=True, timeout=5
        )
        return container in r.stdout.splitlines()
    except Exception:
        return False

def check_process(name: str) -> bool:
    try:
        r = subprocess.run(['pgrep', name], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

def service_status(name: str, cfg: dict) -> dict:
    health = cfg.get('health', {})
    htype  = health.get('type', 'http')

    if htype == 'docker':
        up = check_docker(health['container'])
    elif htype == 'process':
        up = check_process(health['process'])
    else:
        url = health.get('url') or cfg.get('url')
        up  = check_http(url) if url else False

    return {
        'name':        name,
        'label':       cfg['label'],
        'url':         cfg.get('url'),
        'status':      'up' if up else 'down',
        'icon':        cfg.get('icon', 'server'),
        'controllable': True,
        'can_start':   not up and bool(cfg.get('start')),
        'can_stop':    up     and bool(cfg.get('stop')),
    }

# ── Script runner (background) ─────────────────────────────────────────────────

def run_script(path: str) -> None:
    expanded = os.path.expanduser(path)
    try:
        result = subprocess.run(
            ['python3', expanded],
            capture_output=True, text=True, timeout=600
        )
        log.info(f"Script {path}: rc={result.returncode}")
        if result.stdout: log.info(result.stdout[-500:])
        if result.stderr: log.warning(result.stderr[-500:])
    except Exception as e:
        log.error(f"Script {path} failed: {e}")

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'role': 'llmserver', 'time': datetime.now().isoformat()})

@app.route('/api/status')
def api_status():
    if not auth_ok():
        return jsonify({'error': 'Unauthorized'}), 401
    services = load_services()
    return jsonify({
        'services':   [service_status(n, c) for n, c in services.items()],
        'checked_at': datetime.now().isoformat(),
    })

@app.route('/api/service/<name>/start', methods=['POST'])
def start_service(name):
    if not auth_ok():
        return jsonify({'error': 'Unauthorized'}), 401
    services = load_services()
    if name not in services:
        return jsonify({'error': f"Unbekannter Service: {name}"}), 404
    start = services[name].get('start')
    if not start:
        return jsonify({'error': 'Kein start-Befehl konfiguriert'}), 400
    threading.Thread(target=run_script, args=(start['path'],), daemon=True).start()
    return jsonify({'success': True, 'service': name, 'action': 'start'})

@app.route('/api/service/<name>/stop', methods=['POST'])
def stop_service(name):
    if not auth_ok():
        return jsonify({'error': 'Unauthorized'}), 401
    services = load_services()
    if name not in services:
        return jsonify({'error': f"Unbekannter Service: {name}"}), 404
    stop = services[name].get('stop')
    if not stop:
        return jsonify({'error': 'Kein stop-Befehl konfiguriert'}), 400
    threading.Thread(target=run_script, args=(stop['path'],), daemon=True).start()
    return jsonify({'success': True, 'service': name, 'action': 'stop'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8081))
    app.run(host='0.0.0.0', port=port, debug=False)
