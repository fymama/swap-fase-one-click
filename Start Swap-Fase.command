#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "Starting Swap-Fase. First-run setup may take several minutes."
if [ ! -f ".venv/swapfase-install.complete" ] || [ ! -x ".venv/bin/python" ]; then
    if ! ./install.sh --no-models; then
        echo
        echo "Setup failed. Check the message above, then open Start Swap-Fase.command to retry."
        read -r -p "Press Return to close..."
        exit 1
    fi
fi
if [ ! -x ".venv/bin/python" ]; then
    echo "Project-local Python environment was not created."
    read -r -p "Press Return to close..."
    exit 1
fi
".venv/bin/python" run.py
status=$?
if [ "$status" -ne 0 ]; then
    echo
    echo "Swap-Fase stopped with an error. Check the message above."
    read -r -p "Press Return to close..."
fi
exit "$status"
