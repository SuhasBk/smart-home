# 🤖 macOS Smart Home Assistant

A private, locally-hosted voice assistant that turns a MacBook Pro into a dedicated smart home server.

"Jarvis" runs entirely on macOS, orchestrating a headless Home Assistant VM while using local wake-word detection (Porcupine) and cloud-based LLM processing (Gemini 2.5 Flash) to control IoT devices via natural language.

-----

## ⚡️ Features

  * **Hybrid Voice Architecture:**
      * **Always-Listening (Local):** Uses Picovoice Porcupine to detect "Jarvis" instantly with zero latency and high privacy (no audio sent to cloud).
      * **Command Processing (Cloud):** Offloads complex natural language understanding to Google Gemini 2.5 Flash.
  * **Infrastructure as Code:** A single bash script (`start.sh`) manages the VirtualBox VM lifecycle, app launch, and Python execution.
  * **Smart Hardware Management:** Optimized for MacBook servers using **AlDente** (battery health) and **Amphetamine** (sleep prevention).
  * **Robust Error Handling:**
      * Auto-discovery of microphone hardware indices.
      * Home Assistant API health checks before listening.
      * Graceful shutdown trapping (Ctrl+C safely powers down the VM).

-----

## 🛠 Architecture

```mermaid
graph TD
    User((User)) -->|Says 'Jarvis'| Mic[MacBook Mic]
    Mic -->|Raw Audio| PV[Porcupine (Local)]
    PV -->|Wake Event| Py[jarvis.py]
    
    Py -->|Record Command| SR[Google SpeechRec]
    SR -->|Text| LLM[Gemini 2.5 Flash]
    LLM -->|JSON Intent| Py
    
    Py -->|API Call| HA[Home Assistant OS (VM)]
    HA -->|Zigbee/WiFi| Light[Lights]
    HA -->|Cloud| Lock[SmartRent Lock]
```

-----

## 📋 Prerequisites

### Hardware

  * **MacBook (Intel or M-Series):** Used as the always-on server.
  * **Microphone:** Built-in or USB.

### Software

  * **VirtualBox 7.x:** Running Home Assistant OS (HAOS) in "Bridged Mode" (Static IP recommended).
  * **Python 3.10+**
  * **Utilities:**
      * [AlDente](https://apphousekitchen.com/) (Free version is fine) - Limit charge to 75%.
      * [Amphetamine](https://apps.apple.com/us/app/amphetamine/id937984704) - Prevent system sleep.

### API Keys Needed

1.  **Picovoice AccessKey:** For wake word detection ([Console](https://console.picovoice.ai/)).
2.  **Google Gemini API Key:** For natural language processing ([AI Studio](https://aistudio.google.com/)).
3.  **Home Assistant Token:** Long-lived access token from your HA profile.

-----

## 🚀 Installation

### 1\. Clone & Prepare

```bash
git clone https://github.com/SuhasBk/smart-home.git
cd smart-home
```

### 2\. Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

### 3\. System Configuration (Crucial)

  * **VirtualBox:** Ensure your VM is named exactly **"HAOS"** (or update `.env`).
  * **Microphone Permissions:**
    If you see audio errors, reset macOS privacy database:
    ```bash
    tccutil reset Microphone
    ```

### 4\. Configuration (`.env`)

Create a file named `.env` in the root directory:

```ini
# --- SECRETS ---
PICOVOICE_ACCESS_KEY="your_picovoice_key_here"
GEMINI_API_KEY="your_gemini_key_here"
HA_TOKEN="your_long_lived_ha_token"
HA_URL="http://192.168.1.XX:8123"  # Use your Static IP

# --- HARDWARE ---
MIC_NAME="MacBook Pro Microphone"

# --- SYSTEM ---
VM_NAME="HAOS"
SCRIPT_NAME="jarvis.py"
```

-----

## 🖥️ Usage

**One-Click Start:**
Run the orchestration script. This handles booting the VM (if off), launching the VirtualBox app, and starting the voice engine.

```bash
./start_jarvis.sh
```

**Commands:**

  * *"Jarvis, turn on the kitchen lights."*
  * *"Jarvis, secure the apartment."* (Locks door)
  * *"Jarvis, it's too dark in here."* (Gemini infers intent -\> Turns on lights)
  * *"Jarvis, stop."* (Shuts down voice engine)

**Stopping:**
Press `Ctrl+C` in the terminal.

  * The script will ask: `🤔 Do you want to shutdown Home Assistant (HAOS)? [y/N]`
  * **y:** Safely shuts down the VM and quits VirtualBox.
  * **N:** Keeps the server running in the background.

-----

## 🐛 Troubleshooting

| Error | Fix |
| :--- | :--- |
| `PaMacCore (AUHAL)` / Mic Error | Your terminal lacks permission. Run `tccutil reset Microphone` and restart terminal. |
| `Timed out during opening handshake` | Disable **IPv6** in Home Assistant Network settings. |
| `VM failed to start` | Run `VBoxManage discardstate "HAOS"` to clear "Saved/Aborted" states. |
| Script hangs at `(Listening...)` | Ensure ambient noise adjustment is disabled in code. |

-----

## 📜 License

MIT License. Feel free to fork and modify for your own smart home setup.