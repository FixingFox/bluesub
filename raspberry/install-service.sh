#!/bin/bash
# Installs bluesub as a systemd service so it starts on boot and restarts on crash.
# Run with sudo from anywhere, e.g.: sudo ./install-service.sh

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$APP_DIR/venv_pi/bin/python"
SERVICE_NAME="bluesub"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$EUID" -ne 0 ]; then
    echo "[!] Kjør dette scriptet med sudo."
    exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
    echo "[!] Fant ikke $VENV_PYTHON. Kjør ./setup.sh først for å opprette venv_pi."
    exit 1
fi

echo "[+] Konfigurerer eth0..."
"$APP_DIR/configure-network.sh"

echo "[+] Installerer $SERVICE_FILE ..."
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__VENV_PYTHON__|$VENV_PYTHON|g" \
    "$APP_DIR/bluesub.service" > "$SERVICE_FILE"

echo "[+] Laster inn systemd-konfigurasjon på nytt..."
systemctl daemon-reload

echo "[+] Aktiverer tjenesten (start ved oppstart)..."
systemctl enable "$SERVICE_NAME"

echo "[+] Starter tjenesten nå..."
systemctl restart "$SERVICE_NAME"

echo "[✔] Ferdig! Nyttige kommandoer:"
echo "    sudo systemctl status $SERVICE_NAME"
echo "    sudo journalctl -u $SERVICE_NAME -f"
echo "    sudo systemctl restart $SERVICE_NAME"
echo "    sudo systemctl disable $SERVICE_NAME   # slå av autostart"
