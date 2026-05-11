import time
import numpy as np
import pyautogui
import cv2

# Usar Windows Graphics Capture API
try:
    from src.utils.win_capture import capturar_pantalla
    WIN_CAPTURE_OK = True
except ImportError:
    WIN_CAPTURE_OK = False
    import mss  # Fallback

pyautogui.FAILSAFE = False

class GameAI:
    def __init__(self):
        self.running = False
        self.player_mode = 1
        self.screenshot = None
        self.targets = []
        
    def capture_screen(self, region=None):
        """Captura la pantalla usando Windows Graphics Capture API"""
        if WIN_CAPTURE_OK:
            img = capturar_pantalla(region)
            if img is not None:
                # Convertir PIL Image a OpenCV format
                return cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGR)
            return None
        else:
            # Fallback a mss
            with mss.mss() as sct:
                if region:
                    monitor = {"top": region[1], "left": region[0], 
                             "width": region[2], "height": region[3]}
                else:
                    monitor = sct.monitors[1]
                img = sct.grab(monitor)
                return cv2.cvtColor(np.array(img), cv2.COLOR_BGRA2BGR)
    
    def find_color(self, color, region=None, tolerance=10):
        """Encontrar un color en pantalla"""
        screen = self.capture_screen(region)
        h, w, _ = screen.shape
        result = np.where(
            (screen[:,:,0] >= color[0]-tolerance) & (screen[:,:,0] <= color[0]+tolerance) &
            (screen[:,:,1] >= color[1]-tolerance) & (screen[:,:,1] <= color[1]+tolerance) &
            (screen[:,:,2] >= color[2]-tolerance) & (screen[:,:,2] <= color[2]+tolerance)
        )
        if len(result[0]) > 0:
            return (result[1][0], result[0][0])
        return None
    
    def find_click_point(self, region=None):
        """Encontrar punto para hacer click"""
        screen = self.capture_screen(region)
        
        # Convertir a gris
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        
        # Detect edges
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        points = []
        for cnt in contours:
            if cv2.contourArea(cnt) > 100:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    points.append((cx, cy))
        
        return points
    
    def click_at(self, x, y, clicks=1):
        """Hacer click en posición"""
        for _ in range(clicks):
            pyautogui.click(x, y)
            time.sleep(0.1)
    
    def move_at(self, x, y):
        """Mover mouse a posición"""
        pyautogui.moveTo(x, y)
    
    def press_key(self, key):
        """Presionar tecla"""
        pyautogui.press(key)
    
    def hold_key(self, key, duration=0.1):
        """Mantener tecla"""
        pyautogui.keyDown(key)
        time.sleep(duration)
        pyautogui.keyUp(key)
    
    def start(self):
        """Iniciar Game IA"""
        self.running = True
    
    def stop(self):
        """Detener Game IA"""
        self.running = False
    
    def is_running(self):
        """Verificar si está corriendo"""
        return self.running


game_ai = GameAI()