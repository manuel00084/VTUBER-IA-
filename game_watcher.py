import threading
import time
import base64
import io
import requests
from PIL import ImageGrab  # pip install pillow

def capturar_pantalla_base64():
    """Toma screenshot y lo convierte a base64."""
    img = ImageGrab.grab()
    img = img.resize((1280, 720))  # reducir tamaño para no gastar tokens
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def ask_groq_vision(image_b64, api_key, prompt_juego):
    """Manda la imagen a Groq con visión y pide un comentario."""
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # modelo con visión en Groq
            "messages": [
                {
                    "role": "system",
                    "content": prompt_juego
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "¿Qué está pasando en el juego ahora mismo? Comenta brevemente como una VTuber."
                        }
                    ]
                }
            ],
            "max_tokens": 120,
            "temperature": 0.8
        }
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=data,
            headers=headers,
            timeout=20
        )
        if r.status_code != 200:
            print(f"Error visión ({r.status_code}): {r.text}")
            return None
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error game_watcher: {e}")
        return None

class GameWatcher:
    """Hilo que cada N segundos analiza la pantalla y comenta el juego."""
    
    def __init__(self, api_key, speak_fn, stop_audio_fn, get_devices_fn, 
                 current_prompt_fn, intervalo=30, voice="es-MX-DaliaNeural"):
        self.api_key = api_key
        self.speak = speak_fn
        self.stop_audio = stop_audio_fn
        self.get_devices = get_devices_fn
        self.current_prompt = current_prompt_fn
        self.intervalo = intervalo  # segundos entre comentarios
        self.voice = voice
        self.activo = False
        self._thread = None

    def iniciar(self):
        if self.activo:
            return
        self.activo = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("🎮 GameWatcher iniciado")

    def detener(self):
        self.activo = False
        print("🎮 GameWatcher detenido")

    def _loop(self):
        # Prompt especial para comentar juegos
        prompt_juego = (
            self.current_prompt() +
            "\n\nEstás viendo una captura de pantalla del juego que estás transmitiendo. "
            "Haz un comentario divertido, emocionado o gracioso sobre lo que ves. "
            "Máximo 2 oraciones. No repitas lo mismo, varía tus reacciones."
        )
        
        while self.activo:
            time.sleep(self.intervalo)
            if not self.activo:
                break
            try:
                print("📸 Capturando pantalla...")
                img_b64 = capturar_pantalla_base64()
                comentario = ask_groq_vision(img_b64, self.api_key, prompt_juego)
                if comentario:
                    print(f"🎮 Comentario: {comentario}")
                    self.stop_audio()
                    _, ia_dev = self.get_devices()
                    self.speak(comentario, self.voice, ia_dev)
            except Exception as e:
                print(f"Error en loop GameWatcher: {e}")