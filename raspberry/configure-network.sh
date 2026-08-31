#!/bin/bash
# Configures eth0 with the static IP the app expects (PI_IP in main.py), so the
# Pi is always reachable at the same address the laptop/simulator is coded to talk to.
# Run with sudo, e.g.: sudo ./configure-network.sh
#
# Works on both network backends used by Raspberry Pi OS:
#   - NetworkManager (default on Bookworm)
#   - dhcpcd (default on Bullseye and older)

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IFACE="eth0"

if [ "$EUID" -ne 0 ]; then
    echo "[!] Kjør dette scriptet med sudo."
    exit 1
fi

# Pull PI_IP straight from main.py so this script can't drift out of sync with the code
STATIC_IP="$(grep -oP 'PI_IP\s*=\s*"\K[0-9.]+' "$APP_DIR/main.py")"
if [ -z "$STATIC_IP" ]; then
    echo "[!] Klarte ikke å lese PI_IP fra main.py."
    exit 1
fi

PREFIX="24"
GATEWAY="$(echo "$STATIC_IP" | cut -d. -f1-3).1"
DNS="8.8.8.8 1.1.1.1"

echo "[*] Konfigurerer $IFACE med statisk IP $STATIC_IP/$PREFIX (gateway $GATEWAY)..."

if systemctl is-active --quiet NetworkManager; then
    echo "[+] NetworkManager oppdaget, bruker nmcli."
    CON_NAME="bluesub-eth0"

    if nmcli -t -f NAME con show | grep -qx "$CON_NAME"; then
        nmcli con delete "$CON_NAME"
    fi

    nmcli con add type ethernet ifname "$IFACE" con-name "$CON_NAME" \
        ipv4.addresses "$STATIC_IP/$PREFIX" \
        ipv4.gateway "$GATEWAY" \
        ipv4.dns "$DNS" \
        ipv4.method manual \
        connection.autoconnect yes
    nmcli con up "$CON_NAME"

elif [ -f /etc/dhcpcd.conf ]; then
    echo "[+] dhcpcd oppdaget, oppdaterer /etc/dhcpcd.conf."
    MARKER_START="# --- bluesub static ip (start) ---"
    MARKER_END="# --- bluesub static ip (end) ---"

    # Strip any previous bluesub block so re-running this script is idempotent
    sed -i "/$MARKER_START/,/$MARKER_END/d" /etc/dhcpcd.conf

    cat >> /etc/dhcpcd.conf <<EOF
$MARKER_START
interface $IFACE
static ip_address=$STATIC_IP/$PREFIX
static routers=$GATEWAY
static domain_name_servers=$DNS
$MARKER_END
EOF

    echo "[+] Restarter dhcpcd..."
    systemctl restart dhcpcd

else
    echo "[!] Fant hverken NetworkManager eller dhcpcd. Konfigurer $IFACE manuelt."
    exit 1
fi

echo "[✔] $IFACE er satt opp med statisk IP $STATIC_IP."
