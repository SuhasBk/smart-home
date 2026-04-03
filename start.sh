#!/bin/bash

# How this script helps:

# 1. Read required values from .env: $VM_NAME, $SCRIPT_NAME
# 2. Start VirtualBox application if not running
# 3. Start the VM_NAME if not running (idempotent)
# 4. Wait for 2 minutes for HAOS VM to boot up
# 6. Run python script - $SCRIPT_NAME
# 7. Run cleanup (stop VM and exit VirtualBox app) in these scenarios:
#     a. Python script exits normally.
#     b. User triggers Ctrl + C

# --- SETUP CONFIG ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

echo "=================================="
echo "   🤖 INITIALIZING JARVIS...      "
echo "=================================="

# --- STEP 1: LOAD .ENV VARIABLES ---
if [ -f "$ENV_FILE" ]; then
    echo "📜 Loading configuration from .env..."
    
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "❌ Error: .env file not found at $ENV_FILE"
    exit 1
fi

# Verify required variables
if [ -z "$VM_NAME" ] || [ -z "$SCRIPT_NAME" ]; then
    echo "❌ Error: VM_NAME or SCRIPT_NAME missing in .env file."
    echo "   (Check if your .env file is formatted correctly)"
    exit 1
fi

# --- CLEANUP FUNCTION ---
cleanup() {
    echo ""
    echo "🛑 Jarvis (Python) has stopped."
    
    # Prompt user for VM shutdown
    read -r -p "🤔 Do you want to shutdown Home Assistant (HAOS)? [y/N] " response
    
    # FIX: Use 'tr' for lowercase conversion (macOS compatible)
    response=$(echo "$response" | tr '[:upper:]' '[:lower:]')
    
    if [[ "$response" == "y" || "$response" == "yes" ]]; then
        if VBoxManage list runningvms | grep -q "\"$VM_NAME\""; then
            echo "💤 Sending Shutdown signal to '$VM_NAME'..."
            VBoxManage controlvm "$VM_NAME" acpipowerbutton
            
            echo "⏳ Waiting for VM to power off..."
            while VBoxManage list runningvms | grep -q "\"$VM_NAME\""; do
                sleep 1
                printf "."
            done
            echo ""
            echo "✅ VM is off."
        else
            echo "ℹ️  VM was not running."
        fi

        echo "🚪 Quitting VirtualBox Application..."
        osascript -e 'quit app "VirtualBox"'
        echo "👋 Full System Shutdown. Goodbye!"
    else
        echo "✅ Keeping HAOS running in background."
        echo "👋 Jarvis Offline. Goodbye!"
    fi
    
    exit 0
}

# Trap SIGINT (Ctrl+C)
trap cleanup SIGINT

# --- STEP 2: START VIRTUALBOX APP ---
if ! pgrep -x "VirtualBox" > /dev/null; then
    echo "🖥️  Starting VirtualBox App..."
    open -a "VirtualBox"
    sleep 3
fi

if ! command -v VBoxManage &> /dev/null; then
    export PATH=$PATH:/Applications/VirtualBox.app/Contents/MacOS
fi

# --- STEP 3: START VIRTUAL MACHINE ---
if VBoxManage list runningvms | grep -q "\"$VM_NAME\""; then
    echo "✅ VM '$VM_NAME' is already running."
else
    echo "🚀 Booting VM '$VM_NAME' in headless mode..."
    VBoxManage startvm "$VM_NAME" --type headless
    if [ $? -eq 0 ]; then
        echo "⏳ Waiting 2 minutes for Home Assistant..."
        sleep 130
    else
        echo "❌ Error: Failed to start VM '$VM_NAME'."
        exit 1
    fi
fi

# --- STEP 4: START PYTHON SCRIPT ---
echo "📂 Navigating to $SCRIPT_DIR"
cd "$SCRIPT_DIR"

echo "🎤 Launching $SCRIPT_NAME..."
echo "----------------------------------"
echo "ℹ️  Press Ctrl+C to stop Jarvis."

# Run Python
python3 "$SCRIPT_NAME"

# If Python exits normally (not Ctrl+C), run cleanup manually
cleanup