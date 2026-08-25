#!/bin/bash

# Avslutt skriptet umiddelbart hvis en kommando feiler
set -e

echo "[*] Starter oppsett av virtuelt miljø for Raspberry Pi..."

# 1. Opprett virtuelt miljø hvis det ikke eksisterer
if [ ! -d "venv_pi" ]; then
    echo "[+] Oppretter venv_pi..."
    python3 -m venv venv_pi
else
    echo "[*] venv_pi eksisterer allerede."
fi

# 2. Aktiver det virtuelle miljøet
echo "[+] Aktiverer virtuelt miljø..."
source venv_pi/bin/activate

# 3. Oppgrader pip til nyeste versjon
echo "[+] Oppgraderer pip..."
pip install --upgrade pip

# 4. Installer nødvendige avhengigheter
echo "[+] Installerer avhengigheter (rpi.gpio, opencv-python)..."
pip install rpi.gpio opencv-python

echo "[✔] Oppsett fullført! For å starte serveren på Pi-en, kjør:"
echo "    source venv_pi/bin/activate"
echo "    python pi_server.py"
