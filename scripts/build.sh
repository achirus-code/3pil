#!/usr/bin/env bash
# Baut dist/saeulenwaechter.zip (Inhalt von custom_components/saeulenwaechter) für HACS bzw. manuelle Installation.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf dist && mkdir -p dist
(cd custom_components/saeulenwaechter && zip -qr ../../dist/saeulenwaechter.zip . -x '*__pycache__*' '*.pyc' '.DS_Store')
echo "dist/saeulenwaechter.zip ($(du -h dist/saeulenwaechter.zip | cut -f1))"
