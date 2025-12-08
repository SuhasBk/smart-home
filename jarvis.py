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

# --- LOAD SECRETS ---
load_dotenv()

# Get Configuration
HA_URL = os.getenv("HA_URL")
TOKEN = os.getenv("HA_TOKEN")
PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
MIC_NAME = os.getenv("MIC_NAME", "MacBook Pro Microphone")

# --- SAFETY CHECK ---
if not all([HA_URL, TOKEN, PICOVOICE_ACCESS_KEY, GEMINI_API_KEY]):
    print("❌ ERROR: Missing keys in .env file!")
    print("Ensure HA_URL, HA_TOKEN, PICOVOICE_ACCESS_KEY, and GEMINI_API_KEY are set.")
    sys.exit(1)

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# --- HELPER: AUTO-DISCOVER MICS ---
def get_mic_indices(target_name):
    sr_index = None
    pv_index = None
    print(f"🔎 Scanning for '{target_name}'...")

    try:
        mics = sr.Microphone.list_microphone_names()
        for i, name in enumerate(mics):
            if target_name in name:
                sr_index = i
                print(f"   ✅ Found for Google (SR) at Index: {i}")
                break
    except Exception as e:
        print(f"   ❌ SR Scan Error: {e}")

    try:
        devices = PvRecorder.get_available_devices()
        for i, device in enumerate(devices):
            if target_name in device:
                pv_index = i
                print(f"   ✅ Found for Wake Word (PV) at Index: {i}")
                break
    except Exception as e:
        print(f"   ❌ PV Scan Error: {e}")

    if sr_index is None or pv_index is None:
        print(f"⚠️ CRITICAL: Could not find '{target_name}'. Using defaults (3, 1).")
        return (3, 1)
    
    return sr_index, pv_index

# --- THE BRAIN (GEMINI 2.5 FLASH) ---
def ask_gemini_intent(user_text):
    """
    Sends natural language to Gemini and gets a structured JSON command back.
    """
    # Define available tools for the AI
    devices_context = """
    Available Devices & Entities:
    - kitchen_light (switch.kitchen_light)
    - entry_light (switch.entry_light)
    - front_door (lock.front_door_lock)
    """
    
    prompt = f"""
    You are Jarvis, a smart home assistant.
    User said: "{user_text}"
    
    {devices_context}
    
    INSTRUCTIONS:
    1. Determine the user's intent.
    2. If controlling a device, map it to the correct entity_id.
    3. Return a JSON object ONLY. No markdown, no conversational text.
    
    JSON FORMATS:
    [Home Automation]
    {{
      "action": "call_service",
      "domain": "switch" or "lock",
      "service": "turn_on", "turn_off", "unlock", or "lock",
      "entity_id": "switch.kitchen_light"
    }}
    
    [General Chat]
    {{
      "action": "chat",
      "response": "Your short, witty reply here."
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        # Clean up code blocks if Gemini adds them
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
        
    except Exception as e:
        print(f"🧠 Brain Error: {e}")
        return None

def speak(text):
    print(f"Jarvis: {text}")
    os.system(f'say "{text}"')

def check_ha_health():
    url = f"{HA_URL}/api/"
    headers = {"Authorization": f"Bearer {TOKEN}", "content-type": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=2)
        return response.status_code == 200
    except:
        return False

def call_ha_service(domain, service, entity_id):
    url = f"{HA_URL}/api/services/{domain}/{service}"
    headers = {"Authorization": f"Bearer {TOKEN}", "content-type": "application/json"}
    data = {"entity_id": entity_id}
    try:
        requests.post(url, headers=headers, json=data)
        return True
    except:
        return False

def listen_for_command(mic_index):
    r = sr.Recognizer()
    r.energy_threshold = 300 
    r.dynamic_energy_threshold = False 
    
    try:
        with sr.Microphone(device_index=mic_index) as source:
            print("   (Listening for command...)")
            audio = r.listen(source, timeout=2, phrase_time_limit=10)
            print("   Processing...")
            command = r.recognize_google(audio).lower()
            print(f"   You said: {command}")
            return command
    except sr.WaitTimeoutError:
        print("   (Timeout - No speech detected)")
        return None
    except sr.UnknownValueError:
        speak("I didn't catch that.")
        return None
    except sr.RequestError:
        speak("I am offline.")
        return None
    except Exception as e:
        print(f"Mic Error: {e}")
        return 'STOP'

# --- THE LOOP ---
if __name__ == "__main__":
    
    SR_IDX, PV_IDX = get_mic_indices(MIC_NAME)

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

    speak("Jarvis online.")

    try:
        recorder.start()
        while True:
            pcm = recorder.read()
            if porcupine.process(pcm) >= 0:
                print("\n(!) Wake Word Detected")
                recorder.stop()
                
                if check_ha_health():
                    time.sleep(0.5)
                    os.system('afplay /System/Library/Sounds/Tink.aiff')
                    
                    # 1. Listen for the raw command
                    command_text = listen_for_command(SR_IDX)
                    
                    if command_text:
                        # 2. Send to Gemini Brain
                        print("   🧠 Thinking...")
                        decision = ask_gemini_intent(command_text)
                        
                        if isinstance(decision, dict):
                            decision = [decision]
                        
                        if decision:
                            for action_item in decision:
                                action_type = action_item.get("action")
                                
                                # Case A: Control a Device
                                if action_type == "call_service":
                                    domain = action_item.get("domain")
                                    service = action_item.get("service")
                                    entity = action_item.get("entity_id")
                                    
                                    speak(f"Executing {service} on {domain}.")
                                    call_ha_service(domain, service, entity)
                                    time.sleep(1) # Pause slightly between actions
                                
                                # Case B: Just Chat
                                elif action_type == "chat":
                                    speak(action_item.get("response"))
                                    
                        elif command_text == "stop" or command_text == "exit":
                            speak("Shutting down.")
                            break
                        else:
                            speak("I'm not sure what to do with that.")
                else:
                    speak("I cannot reach Home Assistant.")
                
                print("   (Resuming watch...)")
                recorder.start()

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        if recorder is not None: recorder.delete()
        if porcupine is not None: porcupine.delete()