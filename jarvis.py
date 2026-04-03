import requests
import os
import sys
import time
import json
import speech_recognition as sr
import pvporcupine
import google.generativeai as genai
from pvrecorder import PvRecorder
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()

HA_URL = os.getenv("HA_URL")
TOKEN = os.getenv("HA_TOKEN")
PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") 
MIC_NAME = os.getenv("MIC_NAME", "MacBook Pro Microphone")
DEVICES_JSON_STR = os.getenv("DEVICES_JSON", "{}")

# --- SAFETY CHECK ---
if not all([HA_URL, TOKEN, PICOVOICE_ACCESS_KEY, GOOGLE_API_KEY]):
    print("❌ ERROR: Missing keys in .env file!")
    sys.exit(1)

# --- LOAD DEVICES ---
try:
    ENTITIES = json.loads(DEVICES_JSON_STR)
    if not ENTITIES:
        print("⚠️ WARNING: DEVICES_JSON is empty in .env")
except json.JSONDecodeError as e:
    print(f"❌ ERROR: Invalid JSON in .env DEVICES_JSON: {e}")
    sys.exit(1)

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)


# --- HELPER: AUTO-DISCOVER MICS ---
def get_mic_indices(target_name):
    """Finds the correct microphone index for both Google (SR) and Porcupine (PV)"""
    sr_index = None
    pv_index = None
    print(f"🔎 Scanning for '{target_name}'...")
    
    # 1. Google Speech Recognition
    try:
        mics = sr.Microphone.list_microphone_names()
        for i, name in enumerate(mics):
            if target_name in name:
                sr_index = i
                print(f"   ✅ Found for Google (SR) at Index: {i}")
                break
    except Exception: pass

    # 2. Porcupine Wake Word
    try:
        devices = PvRecorder.get_available_devices()
        for i, device in enumerate(devices):
            if target_name in device:
                pv_index = i
                print(f"   ✅ Found for Wake Word (PV) at Index: {i}")
                break
    except Exception: pass

    if sr_index is None or pv_index is None:
        print(f"⚠️ CRITICAL: Could not find '{target_name}'. Using defaults (3, 1).")
        return (3, 1)
    
    return sr_index, pv_index


# --- THE BRAIN (GEMINI 2.5 FLASH) ---
def ask_gemini_intent(user_text):
    """Sends text to Gemini and gets a JSON list of actions."""
    
    # Build list of devices for the AI context
    device_list_str = "\n".join([f"- {name} ({entity_id})" for name, entity_id in ENTITIES.items()])
    
    prompt = f"""
    You are Jarvis, a smart home assistant.
    User said: "{user_text}"
    
    Available Devices:
    {device_list_str}
    
    INSTRUCTIONS:
    1. Identify the user's intent.
    2. Map the friendly name to the 'entity_id'.
    3. Return a JSON list of actions.
    
    SPECIAL HANDLING FOR TV / ROKU:
    - If user says "Open [App Name]" (e.g. YouTube, Netflix), use action: "call_service", domain: "media_player", service: "select_source".
    - You MUST include a "source" field with the exact App Name (e.g. "YouTube").
    
    VALID ACTIONS:
    - Domain: "switch", "light", "lock", "media_player"
    - Service: "turn_on", "turn_off", "unlock", "lock", "media_play", "media_pause", "media_stop", "volume_mute", "select_source"
    
    FORMAT:
    [
      {{
        "action": "call_service",
        "domain": "media_player",
        "service": "select_source",
        "entity_id": "media_player.terminal_vision",
        "source": "YouTube"
      }}
    ]
    
    If general chat, return:
    [ {{ "action": "chat", "response": "Your short reply here." }} ]
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        # Clean markdown if present
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"🧠 Brain Error: {e}")
        return None


# --- SYSTEM ACTIONS ---
def speak(text):
    """Uses macOS native TTS"""
    print(f"Jarvis: {text}")
    os.system(f'say "{text}"')

def check_ha_health():
    """Pings Home Assistant to ensure it's reachable"""
    try:
        requests.get(f"{HA_URL}/api/", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
        return True
    except:
        return False

def call_ha_service(domain, service, entity_id, extra_data=None):
    """Sends command to Home Assistant"""
    url = f"{HA_URL}/api/services/{domain}/{service}"
    headers = {"Authorization": f"Bearer {TOKEN}", "content-type": "application/json"}
    
    data = {"entity_id": entity_id}
    if extra_data:
        data.update(extra_data)
        
    try:
        requests.post(url, headers=headers, json=data)
        return True
    except:
        return False

def listen_for_command(mic_index):
    """Listens for speech with strict timeouts"""
    r = sr.Recognizer()
    r.energy_threshold = 500       # Static threshold for speed
    r.dynamic_energy_threshold = False
    
    try:
        with sr.Microphone(device_index=mic_index) as source:
            os.system('afplay /System/Library/Sounds/Tink.aiff')
            print("   (Listening...)")
            audio = r.listen(source, timeout=3, phrase_time_limit=10)
            print("   Processing...")
            return r.recognize_google(audio).lower()
    except Exception:
        return None


# --- MAIN LOOP ---
if __name__ == "__main__":
    # 1. Setup Hardware
    SR_IDX, PV_IDX = get_mic_indices(MIC_NAME)

    # 2. Initialize Wake Word
    try:
        porcupine = pvporcupine.create(
            access_key=PICOVOICE_ACCESS_KEY,
            keywords=['jarvis'],
            sensitivities=[0.7]
        )
        recorder = PvRecorder(device_index=PV_IDX, frame_length=porcupine.frame_length)
    except Exception as e:
        print(f"Init Error: {e}")
        sys.exit(1)

    # 3. PRE-FLIGHT HEALTH CHECK
    print("🏥 Performing initial health check...")
    if not check_ha_health():
        print("❌ ERROR: Home Assistant is unreachable!")
        print(f"   URL: {HA_URL}")
        speak("System failure. Cannot reach Home Assistant.")
        sys.exit(1)
    
    print("✅ Health check passed.")
    speak(f"Jarvis online. Loaded {len(ENTITIES)} devices.")

    # 4. Start Loop
    try:
        recorder.start()
        while True:
            pcm = recorder.read()
            
            # Check for Wake Word
            if porcupine.process(pcm) >= 0:
                print("\n(!) Wake Word Detected")
                recorder.stop()
                
                # Double-check health (in case it died since start)
                if check_ha_health():
                    time.sleep(0.5) # Wait for mic to unlock
                    
                    # Listen for command
                    command = listen_for_command(SR_IDX)

                    if command in ["stop", "exit", "shut down"]:
                        speak("Goodbye.")
                        break
                    
                    if command:
                        print(f"   🗣️ You said: {command}")
                        print("   🧠 Thinking...")
                        
                        # Ask Gemini
                        decision = ask_gemini_intent(command)
                        
                        # Normalize single object to list
                        if isinstance(decision, dict):
                            decision = [decision]
                        
                        if decision:
                            for action in decision:
                                action_type = action.get("action")
                                
                                # CASE A: Home Automation
                                if action_type == "call_service":
                                    svc = action.get("service")
                                    # Handle extra data (like source for TV)
                                    extra = {}
                                    if "source" in action:
                                        extra["source"] = action["source"]
                                        
                                    speak(f"Executing {svc}.")
                                    call_ha_service(
                                        action.get("domain"), 
                                        svc, 
                                        action.get("entity_id"),
                                        extra_data=extra
                                    )
                                    time.sleep(0.5)
                                
                                # CASE B: General Chat
                                elif action_type == "chat":
                                    speak(action.get("response"))
                    else:
                        print("   (No speech detected)")
                else:
                    speak("Home Assistant is unreachable.")
                
                print("   (Resuming watch...)")
                recorder.start()

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if recorder is not None: recorder.delete()
        if porcupine is not None: porcupine.delete()