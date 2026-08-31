import sys
import os
import socket
import json
import time
import threading
import struct
import cv2
import numpy as np
import pygame

# --- DYNAMISK KONFIGURASJON (RUN PARAMETERS) ---
if "--sim" in sys.argv:
    PI_IP = "127.0.0.1"
    print("[*] KONFIGURASJON: Kjører i SIMULATOR-modus (localhost)")
else:
    PI_IP = "192.168.1.20"
    print("[*] KONFIGURASJON: Kjører i LIVE-modus (Ekte Raspberry Pi)")

TCP_PORT = 5000
UDP_PORT_CAM1 = 5001
UDP_PORT_CAM2 = 5002

def _get_int_arg(flag, default):
    """Read --flag value / --flag=value from argv, falling back to default."""
    for i, arg in enumerate(sys.argv):
        if arg == flag and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                pass
        elif arg.startswith(flag + "="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                pass
    return default

# Layout below is designed against this reference resolution; actual window is scaled to it
BASE_WIDTH, BASE_HEIGHT = 700, 420
SCREEN_WIDTH = _get_int_arg("--width", int(os.environ.get("BLUESUB_SCREEN_WIDTH", BASE_WIDTH)))
SCREEN_HEIGHT = _get_int_arg("--height", int(os.environ.get("BLUESUB_SCREEN_HEIGHT", BASE_HEIGHT)))

PROTOCOL_VERSION = 1
FRAME_HEADER_FORMAT = "!Id"  # sequence number (uint32) + send timestamp (double)
FRAME_HEADER_SIZE = struct.calcsize(FRAME_HEADER_FORMAT)

# Globale variabler og individuelle tidsstempler for videostrømmer
frame_cam1 = None
frame_cam2 = None
last_frame_time_cam1 = 0
last_frame_time_cam2 = 0

# Sekvensnummer-sporing for å oppdage tapte UDP-pakker
last_seq_cam1 = None
last_seq_cam2 = None
lost_frames_cam1 = 0
lost_frames_cam2 = 0

connection_status = "DISCONNECTED"
camera_mode = "DUAL" # Alternativer: "NONE", "CAM1", "CAM2", "DUAL"
control_socket = None

# --- UDP MOTTAK ---
def video_receiver_worker(port, cam_id):
    global frame_cam1, frame_cam2, last_frame_time_cam1, last_frame_time_cam2
    global last_seq_cam1, last_seq_cam2, lost_frames_cam1, lost_frames_cam2
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(("0.0.0.0", port))
    udp_socket.settimeout(0.2)
    
    while True:
        try:
            data, _ = udp_socket.recvfrom(65507)
            if data and len(data) > FRAME_HEADER_SIZE:
                seq, _sent_time = struct.unpack(FRAME_HEADER_FORMAT, data[:FRAME_HEADER_SIZE])
                np_arr = np.frombuffer(data[FRAME_HEADER_SIZE:], dtype=np.uint8)
                decoded_frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if decoded_frame is not None:
                    # Konverter BGR til RGB for Pygame
                    decoded_frame = cv2.cvtColor(decoded_frame, cv2.COLOR_BGR2RGB)
                    
                    if cam_id == 1:
                        if last_seq_cam1 is not None and seq > last_seq_cam1 + 1:
                            lost_frames_cam1 += seq - last_seq_cam1 - 1
                        last_seq_cam1 = seq
                        frame_cam1 = decoded_frame
                        last_frame_time_cam1 = time.time()
                    else:
                        if last_seq_cam2 is not None and seq > last_seq_cam2 + 1:
                            lost_frames_cam2 += seq - last_seq_cam2 - 1
                        last_seq_cam2 = seq
                        frame_cam2 = decoded_frame
                        last_frame_time_cam2 = time.time()
        except socket.timeout:
            pass

# --- HEARTBEAT SENDER (TCP) ---
def heartbeat_worker():
    global control_socket, connection_status
    while True:
        if connection_status == "CONNECTED" and control_socket:
            try:
                # LAGT TIL: \n for å sikre at JSON ikke pakkes sammen (TCP packet concatenation)
                heartbeat_packet = json.dumps({"type": "HEARTBEAT", "v": PROTOCOL_VERSION}) + "\n"
                control_socket.sendall(heartbeat_packet.encode('utf-8'))
            except socket.error:
                connection_status = "DISCONNECTED"
        time.sleep(0.1)

# --- AUTO-RECONNECT MANAGER ---
def connection_manager():
    global control_socket, connection_status, camera_mode
    while True:
        if connection_status == "DISCONNECTED":
            try:
                if control_socket:
                    control_socket.close()
                control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                control_socket.settimeout(1.0)
                control_socket.connect((PI_IP, TCP_PORT))
                connection_status = "CONNECTED"
                send_camera_mode(camera_mode)
            except socket.error:
                connection_status = "DISCONNECTED"
                time.sleep(1.0)
        time.sleep(0.5)

# --- SENDINGS-FUNKSJONER ---
def send_control(motor, direction):
    global control_socket, connection_status
    if connection_status == "CONNECTED" and control_socket:
        try:
            cmd = json.dumps({"type": "CONTROL", "motor": motor, "dir": direction, "v": PROTOCOL_VERSION}) + "\n"
            control_socket.sendall(cmd.encode('utf-8'))
        except socket.error:
            connection_status = "DISCONNECTED"

def send_camera_mode(mode):
    global control_socket, connection_status
    if connection_status == "CONNECTED" and control_socket:
        try:
            cmd = json.dumps({"type": "CAM_MODE", "mode": mode, "v": PROTOCOL_VERSION}) + "\n"
            control_socket.sendall(cmd.encode('utf-8'))
        except socket.error:
            connection_status = "DISCONNECTED"

# --- HELPER FOR Å TEGNE "NO FEED" PLAKAT ---
def draw_no_feed_placeholder(surface, rect_area, text_font):
    """Tegner en ren mørkegrå boks med rød advarsel og teksten 'NO FEED'."""
    pygame.draw.rect(surface, (35, 35, 35), rect_area)
    pygame.draw.rect(surface, (200, 50, 50), rect_area, 2) # Rød ramme
    
    # Sentrer teksten i den tildelte boksen
    txt_surf = text_font.render("NO FEED", True, (220, 70, 70))
    txt_rect = txt_surf.get_rect(center=(rect_area[0] + rect_area[2]//2, rect_area[1] + rect_area[3]//2))
    surface.blit(txt_surf, txt_rect)

# --- PYGAME GRENRESNITT ---
def main():
    global camera_mode, connection_status, frame_cam1, frame_cam2
    
    # Scale factors map the fixed BASE_WIDTH x BASE_HEIGHT layout onto the configured window size
    scale_x = SCREEN_WIDTH / BASE_WIDTH
    scale_y = SCREEN_HEIGHT / BASE_HEIGHT
    
    def scale_rect(x, y, w, h):
        return (int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y))
    
    def scale_pos(x, y):
        return (int(x * scale_x), int(y * scale_y))
    
    def scale_font(size):
        return max(8, int(size * min(scale_x, scale_y)))
    
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Pi 4 Mission Control Panel")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", scale_font(15))
    bold_font = pygame.font.SysFont("Arial", scale_font(20), bold=True)
    feed_font = pygame.font.SysFont("Arial", scale_font(24), bold=True)
    
    # Start bakgrunnstråder
    threading.Thread(target=video_receiver_worker, args=(UDP_PORT_CAM1, 1), daemon=True).start()
    threading.Thread(target=video_receiver_worker, args=(UDP_PORT_CAM2, 2), daemon=True).start()
    threading.Thread(target=connection_manager, daemon=True).start()
    threading.Thread(target=heartbeat_worker, daemon=True).start()
    
    last_states = {1: "STOP", 2: "STOP", 3: "STOP", 4: "STOP"}
    
    running = True
    while running:
        screen.fill((25, 25, 25))
        
        # 1. Håndter Kameratoggle
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                new_mode = None
                if event.key == pygame.K_0: new_mode = "NONE"
                elif event.key == pygame.K_1: new_mode = "CAM1"
                elif event.key == pygame.K_2: new_mode = "CAM2"
                elif event.key == pygame.K_3: new_mode = "DUAL"
                
                if new_mode and new_mode != camera_mode:
                    camera_mode = new_mode
                    send_camera_mode(camera_mode)
        
        # 2. Håndter Motorstyring
        keys = pygame.key.get_pressed()
        current_states = {
            1: "FORWARD" if keys[pygame.K_w] else ("REVERSE" if keys[pygame.K_s] else "STOP"),
            2: "FORWARD" if keys[pygame.K_i] else ("REVERSE" if keys[pygame.K_k] else "STOP"),
            3: "FORWARD" if keys[pygame.K_a] else ("REVERSE" if keys[pygame.K_d] else "STOP"),
            4: "FORWARD" if keys[pygame.K_j] else ("REVERSE" if keys[pygame.K_l] else "STOP")
        }
        
        for m_id, state in current_states.items():
            if state != last_states[m_id]:
                send_control(m_id, state)
                last_states[m_id] = state
                
        # 3. Beregn sanntids pakketilstand for hvert enkelt kamera (0.5s maks forsinkelse tillatt)
        now = time.time()
        cam1_alive = (now - last_frame_time_cam1 < 0.5) if camera_mode in ["CAM1", "DUAL"] else False
        cam2_alive = (now - last_frame_time_cam2 < 0.5) if camera_mode in ["CAM2", "DUAL"] else False
        
        # 4. Tegn videofeltet basert på gjeldende modus og tilstand
        # Videolerretet starter i posisjon X=30, Y=30 med dimensjon 640x240 (før skalering)
        if camera_mode == "NONE":
            draw_no_feed_placeholder(screen, scale_rect(30, 30, 640, 240), feed_font)
            
        elif camera_mode == "CAM1":
            if cam1_alive and frame_cam1 is not None:
                rx, ry, rw, rh = scale_rect(30, 30, 640, 240)
                img = cv2.resize(frame_cam1, (rw, rh))
                surf = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
                screen.blit(surf, (rx, ry))
            else:
                draw_no_feed_placeholder(screen, scale_rect(30, 30, 640, 240), feed_font)
                
        elif camera_mode == "CAM2":
            if cam2_alive and frame_cam2 is not None:
                rx, ry, rw, rh = scale_rect(30, 30, 640, 240)
                img = cv2.resize(frame_cam2, (rw, rh))
                surf = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
                screen.blit(surf, (rx, ry))
            else:
                draw_no_feed_placeholder(screen, scale_rect(30, 30, 640, 240), feed_font)
                
        elif camera_mode == "DUAL":
            # Venstre boks (Kamera 1)
            rx1, ry1, rw1, rh1 = scale_rect(30, 30, 320, 240)
            if cam1_alive and frame_cam1 is not None:
                img1 = cv2.resize(frame_cam1, (rw1, rh1))
                surf1 = pygame.surfarray.make_surface(np.transpose(img1, (1, 0, 2)))
                screen.blit(surf1, (rx1, ry1))
            else:
                draw_no_feed_placeholder(screen, (rx1, ry1, rw1, rh1), feed_font)
                
            # Høyre boks (Kamera 2)
            rx2, ry2, rw2, rh2 = scale_rect(350, 30, 320, 240)
            if cam2_alive and frame_cam2 is not None:
                img2 = cv2.resize(frame_cam2, (rw2, rh2))
                surf2 = pygame.surfarray.make_surface(np.transpose(img2, (1, 0, 2)))
                screen.blit(surf2, (rx2, ry2))
            else:
                draw_no_feed_placeholder(screen, (rx2, ry2, rw2, rh2), feed_font)

        # 5. Tekst og statuslinjer
        mode_text = font.render(f"Aktiv Modus: {camera_mode}  |  Bytt modus: 0=Av, 1=Cam1, 2=Cam2, 3=Dual", True, (220, 220, 220))
        screen.blit(mode_text, scale_pos(30, 285))
        
        inst_text = font.render("Motorer: M1 (W/S)  |  M2 (I/K)  |  M3 (A/D)  |  M4 (J/L)", True, (160, 160, 160))
        screen.blit(inst_text, scale_pos(30, 315))
        
        loss_text = font.render(f"Tapte bilder - Cam1: {lost_frames_cam1}  |  Cam2: {lost_frames_cam2}", True, (160, 160, 160))
        screen.blit(loss_text, scale_pos(30, 335))
        
        # Systemets overordnede nettverksindikator
        is_system_lagging = (camera_mode == "CAM1" and not cam1_alive) or \
                             (camera_mode == "CAM2" and not cam2_alive) or \
                             (camera_mode == "DUAL" and (not cam1_alive or not cam2_alive))
                             
        if connection_status != "CONNECTED":
            status_surface = bold_font.render("SYSTEM STATUS: SØKER ETTER RASPBERRY PI...", True, (255, 165, 0))
        elif is_system_lagging and camera_mode != "NONE":
            status_surface = bold_font.render("SYSTEM STATUS: VIDEO FORSINKELSE DETEKTERT!", True, (255, 0, 0))
        else:
            status_surface = bold_font.render("SYSTEM STATUS: OK (TILKOBLET)", True, (0, 255, 0))
            
        screen.blit(status_surface, scale_pos(30, 355))
        
        pygame.display.flip()
        clock.tick(30)
        
    pygame.quit()

if __name__ == "__main__":
    main()
