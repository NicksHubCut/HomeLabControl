# Homelab auf All-Inkl deployen

## Voraussetzungen
- All-Inkl Hosting mit Python-Unterstützung (Managed Plus oder höher)
- SSH-Zugang (All-Inkl bietet das ab bestimmten Paketen)
- Phusion Passenger ist bei All-Inkl aktiv

---

## 1. Abhängigkeiten installieren

```bash
# Per SSH einloggen
ssh DEIN_USERNAME@ssh.ALL-INKL-DOMAIN.de

# Ins Webroot wechseln
cd /www/htdocs/DEIN_USERNAME/

# Projekt hochladen (oder per SFTP/FTP)
# Dann Pakete installieren:
pip3 install --user -r homelab/requirements.txt
```

Falls `pip3 install --user` nicht geht:
```bash
pip3 install --target=/www/htdocs/DEIN_USERNAME/homelab/vendor -r homelab/requirements.txt
```
Dann in `passenger_wsgi.py` ganz oben ergänzen:
```python
sys.path.insert(0, str(BASE_DIR / "vendor"))
```

---

## 2. .htpasswd erstellen (erste Auth-Schicht)

```bash
# Passwort-Datei anlegen (AUSSERHALB des Webroots!)
htpasswd -c /www/htdocs/DEIN_USERNAME/homelab/.htpasswd dein_benutzername
# Passwort eingeben → fertig
```

Oder online generieren: https://www.htaccesstools.com/htpasswd-generator/
Dann die Datei manuell anlegen mit dem generierten Hash.

---

## 3. .env anlegen

```bash
cp homelab/.env.example homelab/.env
nano homelab/.env   # oder per SFTP bearbeiten
```

Token-Hash generieren:
```bash
python3 -c "import hashlib; print(hashlib.sha256(b'DEIN-TOKEN').hexdigest())"
```

---

## 4. .htaccess anpassen

In `homelab/.htaccess` diese Zeile anpassen:
```
PassengerAppRoot /www/htdocs/DEIN_USERNAME/homelab
```
→ Ersetze `DEIN_USERNAME` mit deinem echten All-Inkl-Username.

---

## 5. Dateistruktur auf dem Server

```
/www/htdocs/DEIN_USERNAME/homelab/
├── .htaccess          ← Passenger + Basic Auth
├── .htpasswd          ← Basic Auth Passwörter
├── .env               ← API Token Hash + Hosts
├── passenger_wsgi.py  ← Einstiegspunkt
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── auth.py
│   ├── audit.py
│   ├── executor.py
│   ├── ratelimit.py
│   └── registry.py
├── services/
│   └── services.yml
├── logs/              ← wird automatisch erstellt
└── ui/
    └── index.html
```

---

## 6. Passenger neu starten

All-Inkl startet Passenger automatisch beim ersten Request.
Zum manuellen Neustart:
```bash
touch /www/htdocs/DEIN_USERNAME/homelab/tmp/restart.txt
```
(Ordner `tmp/` anlegen falls nicht vorhanden)

---

## 7. Testen

```bash
# Health-Check (braucht noch kein Token)
curl -u htpasswd_user:htpasswd_pass https://DEINE-DOMAIN.de/health

# API mit Token
curl -u htpasswd_user:htpasswd_pass \
     -H "Authorization: Bearer DEIN-TOKEN" \
     https://DEINE-DOMAIN.de/api/status
```

---

## Troubleshooting

| Problem | Lösung |
|---|---|
| `500 Internal Server Error` | `logs/` Ordner fehlt oder Rechte falsch |
| `403 Forbidden` | `.htpasswd` Pfad in `.htaccess` prüfen |
| `401 Unauthorized` | API_TOKEN_HASH in `.env` prüfen |
| Module nicht gefunden | `pip3 install --user -r requirements.txt` nochmal |
| Passenger startet nicht | Passenger-Log bei All-Inkl im KAS prüfen |

---

## Security-Checkliste

- [x] `.env` ist per `.htaccess` blockiert (`.env`-Muster)
- [x] `.htpasswd` liegt im Webroot (durch FilesMatch blockiert)
- [x] API-Token via SHA-256 Hash gespeichert, nie im Klartext
- [x] Rate Limiting: 30 Requests/Minute pro IP
- [x] Alle Aktionen werden im Audit-Log erfasst
- [ ] HTTPS aktivieren (Let's Encrypt im All-Inkl KAS)
- [ ] `logs/` Ordner außerhalb des Webroots legen (empfohlen)
