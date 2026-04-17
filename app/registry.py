"""
Service Registry
Liest services.yml und prüft Erreichbarkeit per HTTP/ICMP
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import yaml
import httpx


class ServiceRegistry:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self._services: dict = {}
        self._load()

    def _load(self):
        if not self.config_path.exists():
            self._services = {}
            return
        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        self._services = data.get("services", {})

    def reload(self):
        self._load()

    def get_all(self) -> dict:
        return self._services

    def get(self, name: str) -> Optional[dict]:
        return self._services.get(name)

    async def check_all(self) -> list[dict]:
        """Prüft alle Services parallel"""
        tasks = [
            self._check_service(name, cfg)
            for name, cfg in self._services.items()
        ]
        return await asyncio.gather(*tasks)

    async def _check_service(self, name: str, cfg: dict) -> dict:
        url = cfg.get("url") or cfg.get("health_url")
        status = "unknown"
        latency_ms = None

        if url:
            try:
                import time
                t0 = time.monotonic()
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(url)
                latency_ms = round((time.monotonic() - t0) * 1000)
                status = "up" if r.status_code < 400 else "degraded"
            except Exception:
                status = "down"

        return {
            "name": name,
            "label": cfg.get("label", name),
            "url": cfg.get("url"),
            "status": status,
            "latency_ms": latency_ms,
            "icon": cfg.get("icon", "server"),
            "tags": cfg.get("tags", []),
            "mac": cfg.get("mac"),
            "wol": bool(cfg.get("mac")),
        }

    async def fetch_metrics(self) -> list[dict]:
        """Liest Node-Exporter Endpoints aus ENV"""
        endpoints = []
        for key, val in os.environ.items():
            if key.endswith("_NODE_EXPORTER"):
                name = key.replace("_NODE_EXPORTER", "").lower()
                endpoints.append((name, f"http://{val}/metrics"))

        results = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, url in endpoints:
                try:
                    r = await client.get(url)
                    metrics = self._parse_prometheus(r.text)
                    results.append({"host": name, "metrics": metrics, "status": "ok"})
                except Exception as e:
                    results.append({"host": name, "metrics": {}, "status": "error", "error": str(e)})
        return results

    async def fetch_gpu_metrics(self) -> list[dict]:
        """GPU-Metriken vom GPU-Exporter"""
        gpu_exporter = os.environ.get("LLM_GPU_EXPORTER")
        if not gpu_exporter:
            return []

        url = f"http://{gpu_exporter}/metrics"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url)
            raw = self._parse_prometheus(r.text)

            # Relevante GPU-Metriken extrahieren
            gpu_metrics = {}
            for key, val in raw.items():
                if any(x in key for x in ["gpu", "memory", "temperature", "utilization", "power"]):
                    gpu_metrics[key] = val

            return [{"source": gpu_exporter, "metrics": gpu_metrics, "status": "ok"}]
        except Exception as e:
            return [{"source": gpu_exporter, "metrics": {}, "status": "error", "error": str(e)}]

    def _parse_prometheus(self, text: str) -> dict:
        """Parst Prometheus-Text-Format in dict"""
        result = {}
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            try:
                if " " in line:
                    key, val = line.rsplit(" ", 1)
                    # Nur Basisname ohne Labels für die Übersicht
                    base = key.split("{")[0]
                    result[base] = float(val)
            except Exception:
                continue
        return result
