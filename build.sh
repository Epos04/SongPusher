#!/usr/bin/env bash
# Exit on error
set -o errexit

# Python-Abhängigkeiten installieren
pip install -r requirements.txt

# Node.js-Abhängigkeiten installieren und CSS bauen
npm install
npm run build