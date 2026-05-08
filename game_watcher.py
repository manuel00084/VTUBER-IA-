"""
game_watcher.py — Comentarista de juego dinámico
- Rota entre modelos de visión para evitar rate limit
- Comentarios variados con 6 estilos de reacción
- Backoff inteligente: si falla un modelo, prueba el siguiente
- Nunca repite el mismo estilo dos veces seguidas
"""

import threading
import time
import base64
import io
import traceback
import random
import requests

try:
    from PIL import ImageGrab
    PIL_OK = True
except ImportError:
    PIL_OK = False


# ── Modelos de visión disponibles en Groq (se rotan automáticamente) ─────────
MODELOS_VISION = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]

# ── Estilos de comentario (varían dinámicamente) ──────────────────────────────
ESTILOS = [
    {
        "nombre": "emocionada",
        "instruccion": (
            "Reacciona con emoción y energía alta a lo que ves en el juego. "
            "Usa exclamaciones. Sé espontánea. Máximo 2 oraciones cortas."
        ),
    },
    {
        "nombre": "sarcástica",
        "instruccion": (
            "Comenta lo que ves con humor sarcástico o irónico, como si ya lo hubieras visto todo. "
            "Sé divertida y un poco exagerada. Máximo 2 oraciones."
        ),
    },
    {
        "nombre": "asustada",
        "instruccion": (
            "Reacciona como si la situación del juego te pusiera nerviosa o asustada, "
            "aunque sea algo normal. Sé dramática y graciosa. Máximo 2 oraciones."
        ),
    },
    {
        "nombre": "analítica",
        "instruccion": (
            "Comenta lo que ves como si fuera una experta en el juego, dando una observación "
            "inteligente o estratégica sobre la situación. Máximo 2 oraciones."
        ),
    },
    {
        "nombre": "curiosa",
        "instruccion": (
            "Reacciona con curiosidad genuina sobre algo que ves en pantalla, "
            "como si acabaras de notar algo interesante. Máximo 2 oraciones."
        ),
    },
    {
        "nombre": "cómica",
        "instruccion": (
            "Haz un comentario completamente absurdo o fuera de lugar sobre lo que ves, "
            "como si tuvieras una interpretación muy peculiar de la situación. Máximo 2 oraciones."
        ),
    },
]


def _capturar_base64(bbox=None) -> str:
    img = ImageGrab.grab(bbox=bbox)
    img = img.resize((1024, 576))          # un poco más pequeño = menos tokens
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=65)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _limpiar(texto: str) -> str:
    for c in ["*", "#", "`", "_"]:
        texto = texto.replace(c, "")
    return texto.strip()


def _llamar_groq(img_b64: str, api_key: str, sistema: str, modelo: str) -> str | None:
    """
    Hace UNA llamada a Groq con el modelo dado.
    Devuelve el texto si OK, None si rate limit, lanza excepción en otro error.
    """
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
    data = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": sistema},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                    },
                    {
                        "type": "text",
                        "text": "Comenta brevemente lo que ves en el juego."
                    }
                ]
            }
        ],
        "max_tokens": 100,
        "temperature": 0.9
    }
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=data, headers=headers, timeout=28
    )

    if r.status_code == 429:
        return None                         # rate limit en este modelo

    if r.status_code == 400:
        # Algunos modelos no soportan visión en ciertos estados
        raise ValueError(f"Bad request ({modelo})")

    if r.status_code != 200:
        raise ConnectionError(f"HTTP {r.status_code}: {r.text[:120]}")

    return _limpiar(r.json()["choices"][0]["message"]["content"])


def _analizar(img_b64: str, api_key: str, prompt_vtuber: str,
              estilo: dict, modelo_idx: int, modelos: list, log) -> tuple[str | None, int]:
    """
    Intenta analizar la imagen rotando modelos si hay rate limit.
    Devuelve (comentario_o_None, modelo_idx_usado).
    """
    sistema = (
        f"{prompt_vtuber}\n\n"
        f"Estás viendo una captura de pantalla del juego que transmites en vivo. "
        f"{estilo['instruccion']} "
        f"No empieces con '¡Vaya!' ni 'Oh'. Habla en español, sin markdown."
    )

    total = len(modelos)
    for intento in range(total):
        idx  = (modelo_idx + intento) % total
        mod  = modelos[idx]
        try:
            resultado = _llamar_groq(img_b64, api_key, sistema, mod)
            if resultado is not None:
                return resultado, idx       # éxito
            else:
                log(f"⚠  Rate limit en {mod.split('/')[-1]}, probando siguiente modelo...")
                time.sleep(1.5)             # pequeña pausa antes de intentar el otro
        except ValueError as e:
            log(f"⚠  {e} — saltando modelo")
        except Exception as e:
            log(f"⚠  Error con {mod.split('/')[-1]}: {e}")
            time.sleep(1)

    # Todos los modelos tienen rate limit
    log("⏭  Todos los modelos en rate limit — esperando siguiente ciclo")
    return None, modelo_idx


# ════════════════════════════════════════════════════════════════════════════
class GameWatcher:
    """
    Hilo que captura pantalla cada N segundos y comenta con variedad de estilos.
    Rota modelos automáticamente para evitar rate limit.
    """

    def __init__(self, api_key: str, speak_fn, stop_audio_fn, get_devices_fn,
                 current_prompt_fn, intervalo: int = 25,
                 voice: str = "es-MX-DaliaNeural", log_fn=None):

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

        # Estado interno para variedad
        self._modelo_idx    = 0             # rota entre MODELOS_VISION
        self._ultimo_estilo = -1            # evita repetir estilo consecutivo
        self._historial     = []            # últimos 4 comentarios para no repetir
        self._ciclo         = 0

    # ── Control ──────────────────────────────────────────────────────────────
    def iniciar(self):
        if self.activo:
            self.log("⚠  Comentarista ya estaba activo")
            return
        if not PIL_OK:
            self.log("❌  Falta pillow — pip install pillow")
            return
        if not self.api_key or not self.api_key.strip():
            self.log("❌  Falta GROQ_API_KEY en config.txt")
            return

        self.activo  = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log(f"🎮  Comentarista INICIADO — cada {self.intervalo}s")
        self.log(f"🔄  Modelos disponibles: {len(MODELOS_VISION)} ({', '.join(m.split('/')[-1] for m in MODELOS_VISION)})")
        self.log(f"🎭  Estilos de reacción: {len(ESTILOS)} ({', '.join(e['nombre'] for e in ESTILOS)})")

    def detener(self):
        self.activo = False
        self.log("⏹  Comentarista DETENIDO")

    # ── Loop ─────────────────────────────────────────────────────────────────
    def _loop(self):
        self.log("🎮  [hilo] arrancando...")
        # Primer comentario con un pequeño delay inicial para que se vea el log
        time.sleep(3)

        while self.activo:
            self._ciclo += 1
            self.log(f"🎮  Ciclo #{self._ciclo} — {self.intervalo}s hasta el próximo")
            self._comentar()

            # Esperar en trozos de 1s para poder detener rápido
            for _ in range(self.intervalo):
                if not self.activo:
                    break
                time.sleep(1)

        self.log("🎮  [hilo] finalizado")

    # ── Comentar ─────────────────────────────────────────────────────────────
    def _comentar(self):
        try:
            # Elegir estilo aleatorio (sin repetir el anterior)
            disponibles = [i for i in range(len(ESTILOS)) if i != self._ultimo_estilo]
            estilo_idx  = random.choice(disponibles)
            estilo      = ESTILOS[estilo_idx]
            self._ultimo_estilo = estilo_idx

            self.log(f"📸  Capturando pantalla... (estilo: {estilo['nombre']})")
            img_b64 = _capturar_base64()

            modelo_actual = MODELOS_VISION[self._modelo_idx].split("/")[-1]
            self.log(f"🧠  Analizando con {modelo_actual}...")

            comentario, nuevo_idx = _analizar(
                img_b64,
                self.api_key,
                self.current_prompt(),
                estilo,
                self._modelo_idx,
                MODELOS_VISION,
                self.log
            )
            self._modelo_idx = nuevo_idx

            if not comentario:
                return

            # Verificar que no sea muy similar a comentarios recientes
            if any(comentario[:40] in h for h in self._historial):
                self.log("⏭  Comentario muy similar al anterior, saltando")
                return

            # Guardar en historial (máximo 4)
            self._historial.append(comentario[:60])
            if len(self._historial) > 4:
                self._historial.pop(0)

            self.log(f"🎮  [{estilo['nombre'].upper()}] {comentario}")

            # Vocalizar
            self.stop_audio()
            _, ia_dev = self.get_devices()
            self.speak(comentario, self.voice, ia_dev)

            # Rotar al siguiente modelo para el próximo ciclo (distribuye carga)
            self._modelo_idx = (self._modelo_idx + 1) % len(MODELOS_VISION)

        except Exception as e:
            self.log(f"❌  Error en comentarista: {e}")
            self.log(traceback.format_exc())
