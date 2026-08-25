#!/bin/bash

# Avslutt skriptet umiddelbart hvis en kommando feiler
set -e

echo "[*] Starter oppsett av virtuelt miljø for Laptop..."

# 1. Opprett virtuelt miljø hvis det ikke eksisterer
if [ ! -d "venv_laptop" ]; then
    echo "[+] Oppretter venv_laptop..."
    python3 -m venv venv_laptop
else
    echo "[*] venv_laptop eksisterer allerede."
fi

# 2. Aktiver det virtuelle miljøet
echo "[+] Aktiverer virtuelt miljø..."
source venv_laptop/Scripts/activate

# 3. Oppgrader pip til nyeste versjon
echo "[+] Oppgraderer pip..."
pip install --upgrade pip

# 4. Installer nødvendige avhengigheter
echo "[+] Installerer avhengigheter (opencv-python, pygame, numpy)..."
pip install opencv-python pygame numpy

echo "[✔] Oppsett fullført! For å starte klienten, kjør:"
echo "    source venv_laptop/bin/activate"
echo "    python main.py"
