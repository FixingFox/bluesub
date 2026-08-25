import socket
import json
import time
import threading
import cv2
import numpy as np

# --- SYNTETISK KONFIGURASJON (LOKAL REKKEVIKKE) ---
PI_IP = "127.0.0.1"
LAPTOP_IP = "127.0.0.1"
TCP_PORT = 5000         
UDP_PORT_CAM1 = 5001    
UDP_PORT_CAM2 = 5002    

# Virtuell tilstand på de 8 reléene (0 = OFF, 1 = HIGH)
virtual_gpio = {
    5: 0, 6: 0,   # Motor 1 (fwd, rev)
    12: 0, 13: 0, # Motor 2 (fwd, rev)
    16: 0, 19: 0, # Motor 3 (fwd, rev)
    20: 0, 21: 0  # Motor 4 (fwd, rev)
}

MOTOR_PINS = {
    1: {"fwd": 5,  "rev": 6},
    2: {"fwd": 12, "rev": 13},
    3: {"fwd": 16, "rev": 19},
    4: {"fwd": 20, "rev": 21}
}

last_heartbeat_time = time.time()
watchdog_running = True
current_camera_mode = "DUAL"

def emergency_stop():
    """Simulerer mekanisk nødstopp ved å skru av alle virtuelle reléer."""
    for pin in virtual_gpio:
        virtual_gpio[pin] = 0

def set_motor_state(motor_id, direction):
    """Gjenskaper nøyaktig den samme programvare-forriglingen som på Pi-en."""
    if motor_id not in MOTOR_PINS:
        return
    fwd_pin = MOTOR_PINS[motor_id]["fwd"]
    rev_pin = MOTOR_PINS[motor_id]["rev"]
    
    if direction == "FORWARD":
        virtual_gpio[rev_pin] = 0
        virtual_gpio[fwd_pin] = 1
    elif direction == "REVERSE":
        virtual_gpio[fwd_pin] = 0
        virtual_gpio[rev_pin] = 1
    else:
        virtual_gpio[fwd_pin] = 0
        virtual_gpio[rev_pin] = 0

# --- WATCHDOG TIMEOUT LØKKE ---
def watchdog_loop():
    global last_heartbeat_time
    while watchdog_running:
        if time.time() - last_heartbeat_time > 0.3:
            emergency_stop()
        time.sleep(0.05)

# --- TCP KOMMANDO MOTTAK ---
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
            buffer = ""
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                
                buffer += data.decode('utf-8')
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
                    except json.JSONDecodeError:
                        pass
        except (socket.timeout, socket.error):
            emergency_stop()
        finally:
            try: conn.close()
            except: pass

# --- GENERERING AV SYNTETISK VIDEO (UDP) ---
def synthetic_video_worker(cam_index, port, target_mode_list, color_bg):
    """Genererer animerte testbilder lokalt for å simulere kamera-hardware."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[SIMULATOR] Videotråd startet for Kamera {cam_index} på port {port}")
    
    frame_count = 0
    while watchdog_running:
        if current_camera_mode in target_mode_list:
            start_time = time.time()
            frame_count += 1
            
            # Lag et tomt bilde (320x240) med unik bakgrunnsfarge per kamera
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            frame[:] = color_bg
            
            # Tegn et bevegelig element (en sirkel) for å verifisere bildefrekvens / lag
            cx = int(160 + 80 * np.sin(frame_count * 0.1))
            cy = int(120 + 40 * np.cos(frame_count * 0.15))
            cv2.circle(frame, (cx, cy), 15, (255, 255, 255), -1)
            
            # Legg på tekst-overlegg
            cv2.putText(frame, f"SIMULATED CAM {cam_index}", (15, 35), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(frame, f"Frame: {frame_count}", (15, 210), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            # Komprimer til JPEG og send over UDP
            ret, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
            if ret:
                try:
                    udp_socket.sendto(encoded.tobytes(), (LAPTOP_IP, port))
                except socket.error:
                    pass
            
            elapsed = time.time() - start_time
            time.sleep(max(0.01, 0.05 - elapsed)) # Målrettet ~20 FPS
        else:
            time.sleep(0.1)

# --- DIAGNOSTIKKVINDU FOR SIMULATOR ---
def diagnostic_gui():
    cv2.namedWindow("Raspberry Pi 4 Hardware Simulator", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Raspberry Pi 4 Hardware Simulator", 450, 300)
    
    while watchdog_running:
        panel = np.zeros((300, 450, 3), dtype=np.uint8)
        panel[:] = (40, 40, 40)
        
        cv2.putText(panel, "RPi 4 RELAY MONITOR (LIVE)", (20, 35), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 215, 0), 2)
        
        is_alive = (time.time() - last_heartbeat_time) < 0.3
        status_color = (0, 255, 0) if is_alive else (0, 0, 255)
        status_text = "HEARTBEAT: OK" if is_alive else "HEARTBEAT: TIMEOUT (ESTOP)"
        cv2.putText(panel, status_text, (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1)
        cv2.putText(panel, f"Active Cam Mode: {current_camera_mode}", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        y_offset = 130
        for m_id, pins in MOTOR_PINS.items():
            f_val = virtual_gpio[pins["fwd"]]
            r_val = virtual_gpio[pins["rev"]]
            f_color = (0, 255, 0) if f_val else (160, 160, 160)
            r_color = (0, 255, 0) if r_val else (160, 160, 160)
            
            motor_desc = "STOPPED"
            if f_val: motor_desc = "FORWARD"
            elif r_val: motor_desc = "REVERSE"
            
            cv2.putText(panel, f"Motor {m_id}: [{motor_desc}]", (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(panel, f"Pin {pins['fwd']}(Fwd): {f_val}", (180, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, f_color, 1)
            cv2.putText(panel, f"Pin {pins['rev']}(Rev): {r_val}", (310, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, r_color, 1)
            y_offset += 35
            
        cv2.imshow("Raspberry Pi 4 Hardware Simulator", panel)
        if cv2.waitKey(50) & 0xFF == 27:
            break
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        threading.Thread(target=watchdog_loop, daemon=True).start()
        # Cam 1 (Blåtonet = RGB(20, 20, 120)) | Cam 2 (Rødtonet = RGB(120, 20, 20))
        threading.Thread(target=synthetic_video_worker, args=(1, UDP_PORT_CAM1, ["CAM1", "DUAL"], (120, 20, 20)), daemon=True).start()
        threading.Thread(target=synthetic_video_worker, args=(2, UDP_PORT_CAM2, ["CAM2", "DUAL"], (20, 20, 120)), daemon=True).start()
        threading.Thread(target=tcp_control_server, daemon=True).start()
        diagnostic_gui()
    except KeyboardInterrupt:
        pass
    finally:
        watchdog_running = False
        emergency_stop()
