#!/bin/bash

# --- Activate the virtual environment ---
# Note the path is different on Linux
echo "Activating virtual environment..."
source venv/bin/activate

# --- Show menu ---
echo
echo "What do you want to start?"
echo " 1. Client"
echo " 2. Server"
echo

# --- Get user choice ---
read -p "Enter your choice (1 or 2): " choice

# --- Run based on choice ---
case "$choice" in
  1)
    echo "Starting Client..."
    python client.py
    ;;
  2)
    echo "Starting Server..."
    python server.py
    ;;
  *)
    echo "Invalid choice."
    ;;
esac

echo "Script finished."