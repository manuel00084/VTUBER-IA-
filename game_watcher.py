"""
game_watcher.py — Comentarista de juego en tiempo real
"""
import threading, time, base64, io, traceback, requests

try:
    from PIL import ImageGrab
    PIL_OK = True
except ImportError:
    PIL_OK = False


def _capturar_base64(bbox=None):
    img = ImageGrab.grab(bbox=bbox)
    img = img.resize((1280, 720))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _analizar_con_groq(img_b64, api_key, prompt_vtuber):
    sistema = (
        f"{prompt_vtuber}\n\n"
        "Estás viendo una captura de pantalla del juego que estás transmitiendo. "
        "Haz UN comentario breve, divertido y natural como VTuber. "
        "Máximo 2 oraciones. Varía tus reacciones."
    )
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": "¿Qué está pasando en el juego? Comenta brevemente."}
            ]}
        ],
        "max_tokens": 120,
        "temperature": 0.85
    }
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      json=data, headers=headers, timeout=25)
    if r.status_code == 429:
        return None
    if r.status_code != 200:
        return f"[Error Groq {r.status_code}]"
    texto = r.json()["choices"][0]["message"]["content"].strip()
    for c in ["*", "#", "`", "_"]:
        texto = texto.replace(c, "")
    return texto


class GameWatcher:
    def __init__(self, api_key, speak_fn, stop_audio_fn, get_devices_fn,
                 current_prompt_fn, intervalo=30, voice="es-MX-DaliaNeural", log_fn=None):
        self.api_key        = api_key
        self.speak          = speak_fn
        self.stop_audio     = stop_audio_fn
        self.get_devices    = get_devices_fn
        self.current_prompt = current_prompt_fn
        self.intervalo      = intervalo
        self.voice          = voice
        self.log            = log_fn or print
        self.activo         = False
        self._thread        = None
        self._ultimo        = ""

    def iniciar(self):
        if self.activo:
            self.log("⚠  Comentarista ya estaba activo")
            return
        if not PIL_OK:
            self.log("❌ Comentarista: pip install pillow")
            return
        if not self.api_key or not self.api_key.strip():
            self.log("❌ Comentarista: falta GROQ_API_KEY en config.txt")
            return
        self.activo  = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log(f"🎮 Comentarista INICIADO — cada {self.intervalo}s")

    def detener(self):
        self.activo = False
        self.log("⏹  Comentarista DETENIDO")

    def _loop(self):
        self.log("🎮 [hilo] arrancando...")
        while self.activo:
            for _ in range(self.intervalo):
                if not self.activo:
                    break
                time.sleep(1)
            if not self.activo:
                break
            self._comentar()
        self.log("🎮 [hilo] finalizado")

    def _comentar(self):
        try:
            self.log("📸 Capturando pantalla...")
            img_b64 = _capturar_base64()
            self.log("🧠 Analizando con IA...")
            comentario = _analizar_con_groq(img_b64, self.api_key, self.current_prompt())
            if not comentario:
                self.log("⏭  Sin comentario este ciclo (rate limit)")
                return
            if comentario == self._ultimo:
                self.log("⏭  Pantalla sin cambios, saltando")
                return
            self._ultimo = comentario
            self.log(f"🎮 Comentario: {comentario}")
            self.stop_audio()
            _, ia_dev = self.get_devices()
            self.speak(comentario, self.voice, ia_dev)
        except Exception as e:
            self.log(f"❌ Error comentarista: {e}")
            self.log(traceback.format_exc())
