#!/usr/bin/env bash
# MechLoadout Renamer - lanceur macOS (double-clic : s'ouvre dans Terminal)
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 est introuvable / Python 3 was not found."
    echo "Installe-le depuis / Install it from: https://www.python.org/downloads/"
    read -rp "Entree pour fermer / Enter to close " _
    exit 1
fi

python3 mwobuildmanager.py
status=$?
if [ $status -ne 0 ]; then
    read -rp "Entree pour fermer / Enter to close " _
fi
exit $status
