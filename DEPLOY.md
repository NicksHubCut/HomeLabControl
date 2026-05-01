# Homelab Control – Hybrid Deploy

## Übersicht

```
All-Inkl:   index.html + api.php (nur WoL)
Mini-PC:    api.php (Status, Metriken, GPU, Audit) auf Port 8080
```

---

## Teil 1: Mini-PC einrichten

### 1. PHP installieren
```bash
sudo apt install php php-cli -y
php --version   # sollte PHP 8.x zeigen
```

### 2. API-Verzeichnis anlegen
```bash
mkdir -p ~/homelab-api/{services,logs}
cd ~/homelab-api

# Dateien hierhin kopieren:
# - api.php
# - services/services.json
# - .env.example → .env
```

### 3. .env befüllen
```bash
cp .env.example .env
nano .env
# MINIPC_NODE_EXPORTER=192.168.0.43:9100
# LLM_NODE_EXPORTER=192.168.0.73:9100
# LLM_GPU_EXPORTER=192.168.0.73:9835
```

### 4. services.json anpassen
LLM_MAC eintragen in services/services.json

### 5. Als Systemd-Service einrichten
```bash
# homelab-api.service nach /etc/systemd/system/ kopieren
sudo cp systemd/homelab-api.service /etc/systemd/system/

# DEIN_USERNAME ersetzen
sudo sed -i "s/DEIN_USERNAME/$USER/g" /etc/systemd/system/homelab-api.service

sudo systemctl daemon-reload
sudo systemctl enable --now homelab-api

# Testen:
curl http://localhost:8080/health
# → {"status":"ok","role":"minipc",...}
```

### 6. Tailscale-IP herausfinden
```bash
tailscale ip -4
# → z.B. 100.x.x.x
```
Diese IP bei All-Inkl -> `index.html` eintragen (API_BASE).

### 7. Firewall: Port 8080 nur für Tailscale öffnen
```bash
# Tailscale-Interface ist tailscale0
sudo ufw allow in on tailscale0 to any port 8080
sudo ufw deny 8080   # alle anderen blockieren
```

---

## Teil 2: All-Inkl einrichten

### 1. Dateien hochladen
Per SFTP in den Webroot:
```
/www/htdocs/w015c898/homelab-control.com/
├── .htaccess
├── .htpasswd        ← per SSH anlegen
├── .env             ← nur MAC-Adressen
├── api.php          ← nur WoL
├── index.html       ← UI mit API_BASE angepasst
└── logs/            ← Ordner anlegen
```

### 2. .htpasswd anlegen (SSH)
```bash
cd /www/htdocs/w015c898/homelab-control.com
htpasswd -c .htpasswd deinuser
```

### 4. .env anlegen
```bash
cp .env.example .env
nano .env
# MINIPC_API=http://100.x.x.x:8080   ← Tailscale-IP des Mini-PC
# MINI_PC_MAC=AA:BB:CC:DD:EE:FF
# LLM_SERVER_MAC=AA:BB:CC:DD:EE:FF
```

### 5. logs/ Ordner
```bash
mkdir -p logs && chmod 750 logs
```

---

## Testen

```bash
# 1. Mini-PC API direkt
curl http://100.x.x.x:8080/health
curl http://100.x.x.x:8080/api/status

# 2. All-Inkl WoL (mit htpasswd)
curl -u user:pass -X POST https://homelab-control.com/api/wol/llm-server

# 3. UI aufrufen
# https://homelab-control.com → htpasswd → Dashboard
```

---

## MACs herausfinden
```bash
# Auf dem jeweiligen Rechner:
ip link show | grep "link/ether"
# oder
cat /sys/class/net/enp5s0/address   # Interface-Name anpassen
```

---

## Troubleshooting

| Problem | Lösung |
|---|---|
| API nicht erreichbar | `sudo systemctl status homelab-api` prüfen |
| CORS-Fehler im Browser | Origin in api.php (Mini-PC) prüfen |
| WoL schlägt fehl | MAC in .env (All-Inkl) prüfen |
| Metriken leer | Node Exporter auf beiden Maschinen aktiv? |
| Port 8080 nicht erreichbar | Firewall: `sudo ufw status` |
