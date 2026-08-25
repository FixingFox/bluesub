#!/bin/bash

# Avslutt skriptet umiddelbart hvis en kommando feiler
set -e

echo "[*] Starter oppsett av virtuelt miljø for Raspberry Pi Simulator..."

# 1. Opprett virtuelt miljø hvis det ikke eksisterer
if [ ! -d "venv_simulator" ]; then
    echo "[+] Oppretter venv_simulator..."
    python3 -m venv venv_simulator
else
    echo "[*] venv_simulator eksisterer allerede."
fi

# 2. Aktiver det virtuelle miljøet
echo "[+] Aktiverer virtuelt miljø..."
source venv_simulator/Scripts/activate

# 3. Oppgrader pip til nyeste versjon
echo "[+] Oppgraderer pip..."
pip install --upgrade pip

# 4. Installer nødvendige avhengigheter (kun bildebehandling og matriser)
echo "[+] Installerer avhengigheter (opencv-python, numpy)..."
pip install opencv-python numpy

echo "[✔] Oppsett fullført! For å starte simulatoren, kjør:"
echo "    source venv_simulator/bin/activate"
echo "    python raspberry.py"
