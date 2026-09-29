#!/usr/bin/env bash
# MechLoadout Renamer - lanceur Linux (double-clic ou ./launch_linux.sh)
cd "$(dirname "$(readlink -f "$0")")" || exit 1

# Double-clic depuis un gestionnaire de fichiers : pas de terminal, or le
# programme est interactif -> on se relance dans le premier terminal trouve.
if [ ! -t 0 ] && [ -z "$MWOBM_IN_TERMINAL" ]; then
    export MWOBM_IN_TERMINAL=1
    self="$(readlink -f "$0")"
    for term in x-terminal-emulator konsole gnome-terminal xfce4-terminal kitty alacritty xterm; do
        if command -v "$term" >/dev/null 2>&1; then
            case "$term" in
                gnome-terminal) exec "$term" -- "$self" ;;
                *)              exec "$term" -e "$self" ;;
            esac
        fi
    done
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 est introuvable / Python 3 was not found."
    echo "Installe le paquet python3 de ta distribution / Install your distribution's python3 package."
    read -rp "Entree pour fermer / Enter to close " _
    exit 1
fi

python3 mwobuildmanager.py
status=$?
# garde le terminal ouvert si le programme s'est arrete sur une erreur
if [ $status -ne 0 ]; then
    read -rp "Entree pour fermer / Enter to close " _
fi
exit $status
