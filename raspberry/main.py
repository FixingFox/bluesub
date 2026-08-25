import socket
import json
import time
import threading
import cv2
import RPi.GPIO as GPIO

# --- KONFIGURASJON ---
PI_IP = "192.168.1.20"
LAPTOP_IP = "192.168.1.10"
TCP_PORT = 5000         # Kontroll, Heartbeat og Kamera-kommandoer
UDP_PORT_CAM1 = 5001    # Kamera 1 Video
UDP_PORT_CAM2 = 5002    # Kamera 2 Video

# GPIO Relé-mapping (H-Bridge Par)
MOTOR_PINS = {
    1: {"fwd": 5,  "rev": 6},
    2: {"fwd": 12, "rev": 13},
    3: {"fwd": 16, "rev": 19},
    4: {"fwd": 20, "rev": 21}
}

# Globale sikkerhets- og kameravariabler
last_heartbeat_time = time.time()
watchdog_running = True

# Kameratilstander styrt dynamisk fra Laptop ("NONE", "CAM1", "CAM2", "DUAL")
current_camera_mode = "DUAL" 

# --- GPIO INITIELISERING ---
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for motor, pins in MOTOR_PINS.items():
    GPIO.setup(pins["fwd"], GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(pins["rev"], GPIO.OUT, initial=GPIO.LOW)

def emergency_stop():
    """Slår av alle reléer umiddelbart."""
    for motor, pins in MOTOR_PINS.items():
        GPIO.output(pins["fwd"], GPIO.LOW)
        GPIO.output(pins["rev"], GPIO.LOW)
    print("[FAILSAFE] Nødstopp aktivert: Alle motorer stoppet!")

def set_motor_state(motor_id, direction):
    """Sikker motorstyring med programvare-forrigling (Interlock)."""
    if motor_id not in MOTOR_PINS:
        return
    fwd_pin = MOTOR_PINS[motor_id]["fwd"]
    rev_pin = MOTOR_PINS[motor_id]["rev"]
    
    if direction == "FORWARD":
        GPIO.output(rev_pin, GPIO.LOW)
        GPIO.output(fwd_pin, GPIO.HIGH)
    elif direction == "REVERSE":
        GPIO.output(fwd_pin, GPIO.LOW)
        GPIO.output(rev_pin, GPIO.HIGH)
    else:
        GPIO.output(fwd_pin, GPIO.LOW)
        GPIO.output(rev_pin, GPIO.LOW)

# --- SIKKERHETSWATCHDOG ---
def watchdog_loop():
    global last_heartbeat_time
    while watchdog_running:
        if time.time() - last_heartbeat_time > 0.3:  # 300 ms timeout
            emergency_stop()
            while time.time() - last_heartbeat_time > 0.3 and watchdog_running:
                time.sleep(0.1)
        time.sleep(0.05)

# --- KONTROLLSERVER (TCP) ---
def tcp_control_server():
    global last_heartbeat_time, current_camera_mode
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((PI_IP, TCP_PORT))
    server_socket.listen(1)
    
    print(f"[SIMULATOR] Kontrollserver lytter på TCP {PI_IP}:{TCP_PORT}")
    
    while True:
        try:
            conn, addr = server_socket.accept()
            conn.settimeout(0.5)
            buffer = "" # Buffer til å holde på ufullstendige data
            
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                
                # Dekod dataen og legg den til i bufferen
                buffer += data.decode('utf-8')
                
                # Hvis bufferen inneholder et linjeskift, har vi minst én komplett melding
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.strip():
                        continue
                        
                    last_heartbeat_time = time.time()
                    
                    try:
                        payload = json.loads(line)
                        p_type = payload.get("type")
                        
                        if p_type == "CONTROL":
                            set_motor_state(payload.get("motor"), payload.get("dir"))
                        elif p_type == "CAM_MODE":
                            current_camera_mode = payload.get("mode")
                    except json.JSONDecodeError as je:
                        print(f"[SIMULATOR FEIL] Klarte ikke dekode linje: '{line}' - {je}")
                        
        except (socket.timeout, socket.error):
            emergency_stop()
        finally:
            try: conn.close()
            except: pass


# --- DYNAMISK OPTIMALISERT VIDEOSTRØM (UDP) ---
def video_stream_worker(cam_index, port, target_mode_list):
    """Henter og sender video kun når modusen krever det, frigjør hardware ellers."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cap = None
    
    print(f"[*] Starter videotråd for Kamera {cam_index} (Venter på aktivering...)")
    
    while watchdog_running:
        # Sjekk om dette kameraet skal være aktivt i gjeldende modus
        if current_camera_mode in target_mode_list:
            # Hvis kameraet ikke er åpnet enda, åpne det nå (Våkner fra dvale)
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(cam_index)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                print(f"[+] Kamera {cam_index} AKTIVERT på maskinvarenivå.")
            
            start_time = time.time()
            ret, frame = cap.read()
            if ret:
                ret, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
                if ret:
                    try:
                        udp_socket.sendto(encoded.tobytes(), (LAPTOP_IP, port))
                    except socket.error:
                        pass
            
            elapsed = time.time() - start_time
            sleep_time = max(0.01, 0.05 - elapsed) # ~20 FPS
            time.sleep(sleep_time)
        else:
            # Hvis kameraet er åpent, men modusen sier det skal skrus av (Gå i dvale)
            if cap is not None:
                cap.release()
                cap = None
                print(f"[-] Kamera {cam_index} DEAKTIVERT og frigjort for å spare CPU.")
            time.sleep(0.2) # Lav ressursbruk i dvalemodus
            
    if cap is not None:
        cap.release()

if __name__ == "__main__":
    try:
        threading.Thread(target=watchdog_loop, daemon=True).start()
        
        # Kamera 0 skal kjøre i modus "CAM1" og "DUAL"
        threading.Thread(target=video_stream_worker, args=(0, UDP_PORT_CAM1, ["CAM1", "DUAL"]), daemon=True).start()
        # Kamera 1 skal kjøre i modus "CAM2" og "DUAL"
        threading.Thread(target=video_stream_worker, args=(1, UDP_PORT_CAM2, ["CAM2", "DUAL"]), daemon=True).start()
        
        tcp_control_server()
    except KeyboardInterrupt:
        print("\n[-] Avslutter server...")
    finally:
        watchdog_running = False
        emergency_stop()
        GPIO.cleanup()
