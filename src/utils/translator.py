"""
translator.py — Traductor estilo MORT para VTuber IA
══════════════════════════════════════════════════════
Funciona como MORT:
  • Hotkey global (Ctrl+T) → selecciona área → traduce al instante
  • Hotkey global (Ctrl+R) → repite traducción del área guardada
  • Hotkey global (Ctrl+W) → activa/desactiva traducción continua
  • Overlay de burbujas transparente encima del juego (always-on-top)
  • Panel flotante arrastrable con original + traducción
  • Narrador: si el texto ya está en español → lo lee sin traducir
  • 5 modos de traducción: Natural, Literal, Manga/Anime, RPG/Juego, Narrador
  • Rotación de modelos Groq para evitar rate limit
  • Funciona solo (python translator.py) o integrado al main.py

USO INDEPENDIENTE:
  python translator.py
  Editar GROQ_API_KEY al inicio del archivo o usar config.txt

INTEGRADO EN main.py:
  from translator import TranslatorManager, MODOS, MODO_DEFAULT
"""

import threading
import time
import base64
import io
import json
import re
import sys
import os
import traceback
import tkinter as tk
import tkinter.font as tkfont
import requests

try:
    from PIL import ImageGrab, Image
    PIL_OK = True
except ImportError:
    PIL_OK = False
    print("⚠  Instala pillow: pip install pillow")

# ── Intentar leer config.txt si existe (para modo standalone) ────────────────
def _leer_config():
    rutas = [
        os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.txt"),
        os.path.join(os.path.dirname(__file__), "..", "core", "config.txt"),
    ]
    for ruta in rutas:
        if os.path.exists(ruta):
            cfg = {}
            with open(ruta, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip()
            return cfg
    return {}

# ── Modelos de visión Groq (rota automáticamente) ────────────────────────────
MODELOS_VISION = [
    "llava-v1.5-7b-4096-preview",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]

# ── Modos de traducción ───────────────────────────────────────────────────────
MODOS = {
    "🌐 Natural": {
        "desc": "Traducción fluida y natural",
        "sistema": (
            "Eres un traductor experto. Traduce de forma fluida y natural al {idioma}, "
            "como si el texto fuera escrito originalmente en ese idioma. "
            "Mantén el tono y las emociones del original."
        ),
    },
    "📝 Literal": {
        "desc": "Fiel al original, palabra por palabra",
        "sistema": (
            "Eres un traductor experto. Traduce de forma estrictamente literal al {idioma}, "
            "palabra por palabra. Prioriza la precisión sobre la fluidez."
        ),
    },
    "🌸 Manga/Anime": {
        "desc": "Conserva honoríficos y términos japoneses",
        "sistema": (
            "Eres un traductor experto de manga y anime. Traduce al {idioma} "
            "conservando honoríficos japoneses (san, kun, chan, sama, sensei, senpai), "
            "onomatopeyas y nombres propios sin traducir. "
            "Adapta el estilo al subtitulado de anime."
        ),
    },
    "⚔️ RPG/Juego": {
        "desc": "Estilo narrativo de videojuego RPG",
        "sistema": (
            "Eres un traductor experto de videojuegos RPG. Traduce al {idioma} "
            "usando un estilo épico y formal, conservando nombres de habilidades, "
            "skills e ítems en su idioma original si no tienen traducción establecida."
        ),
    },
    "🎙️ Narrador": {
        "desc": "Lee el texto tal como está, sin traducir",
        "sistema": (
            "Eres un narrador. Si el texto ya está en {idioma}, devuélvelo exactamente igual. "
            "Si está en otro idioma, tradúcelo al {idioma} de forma neutral. "
            "No añadas comentarios ni explicaciones."
        ),
    },
}

MODO_DEFAULT = "🌐 Natural"

# Colores UI
C_BG     = "#1a1b2e"
C_BAR    = "#16172a"
C_CARD   = "#252641"
C_BORD   = "#2e3060"
C_PURP   = "#6441a5"
C_TXT    = "#e2e8f0"
C_MUT    = "#94a3b8"
C_GRN    = "#4ade80"
C_RED    = "#f87171"
C_AMB    = "#fcd34d"
C_LOGBG  = "#0f1117"


# ════════════════════════════════════════════════════════════════════════════
#  GROQ VISION OCR + TRADUCCIÓN
# ════════════════════════════════════════════════════════════════════════════
def _img_a_b64(img) -> str:
    """Convierte imagen PIL a base64 JPEG optimizado."""
    w, h = img.size
    # Redimensionar si es muy grande (ahorra tokens)
    if w > 1280:
        ratio = 1280 / w
        img = img.resize((1280, int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _construir_prompt_sistema(modo: str, idioma: str) -> str:
    base = MODOS.get(modo, MODOS[MODO_DEFAULT])["sistema"].format(idioma=idioma)
    return f"""{base}

INSTRUCCIONES DE RESPUESTA (JSON ESTRICTO):
Analiza la imagen y detecta TODO el texto visible.
Para cada bloque de texto indica su posición aproximada (x_pct, y_pct: porcentaje 0.0-1.0 del tamaño de imagen).

Responde ÚNICAMENTE con este JSON, sin markdown ni texto extra:
{{
  "idioma_detectado": "japonés",
  "es_idioma_destino": false,
  "texto_completo": "todo el texto original",
  "traduccion_completa": "toda la traducción",
  "bloques": [
    {{
      "original": "texto del bloque",
      "traduccion": "traducción del bloque",
      "x_pct": 0.5,
      "y_pct": 0.3,
      "es_idioma_destino": false
    }}
  ]
}}

Si no hay texto: {{"idioma_detectado":"ninguno","es_idioma_destino":true,"texto_completo":"","traduccion_completa":"","bloques":[]}}"""


def _parsear_respuesta(content: str) -> dict | None:
    """Intenta parsear el JSON de Groq, tolerante a errores."""
    content = re.sub(r"```json|```", "", content).strip()
    try:
        return json.loads(content)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return None


def _llamar_groq(img_b64: str, api_key: str, sistema: str, modelo: str) -> dict | None:
    """Llama a Groq Vision. Devuelve dict, {"__rate_limit":True} o None."""
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
    data = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": "Detecta y traduce todo el texto de la imagen."}
            ]}
        ],
        "max_tokens": 700,
        "temperature": 0.05,
    }
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=data, headers=headers, timeout=30
        )
        if r.status_code == 429:
            return {"__rate_limit": True}
        if r.status_code != 200:
            return {"__error": f"HTTP {r.status_code}"}
        content = r.json()["choices"][0]["message"]["content"].strip()
        return _parsear_respuesta(content) or {"__parse_error": content[:100]}
    except requests.exceptions.Timeout:
        return {"__timeout": True}
    except Exception as e:
        return {"__exception": str(e)}


def traducir_imagen(img, api_key: str, modo: str, idioma: str,
                    modelo_idx: int, log=print, motor: str = "Groq (OCR)") -> tuple[dict | None, int]:
    """
    Traduce una imagen PIL usando el motor seleccionado.
    Devuelve (resultado_dict, nuevo_modelo_idx).
    """
    sistema = _construir_prompt_sistema(modo, idioma)
    img_b64 = _img_a_b64(img)
    
    if motor == "Google":
        return _traducir_google(img, idioma, log)
    elif motor == "DeepL":
        return _traducir_deepl(img, api_key, idioma, log)
    elif motor == "LibreTranslate":
        return _traducir_libretranslate(img, idioma, log)
    elif motor == "MyMemory":
        return _traducir_mymemory(img, idioma, log)
    else:
        return _traducir_groq(img_b64, api_key, sistema, modelo_idx, log)


def _traducir_groq(img_b64: str, api_key: str, sistema: str, modelo_idx: int, log) -> tuple[dict | None, int]:
    """Traduce usando Groq Vision."""
    total = len(MODELOS_VISION)
    for intento in range(total):
        idx = (modelo_idx + intento) % total
        mod = MODELOS_VISION[idx]
        res = _llamar_groq(img_b64, api_key, sistema, mod)
        
        if res is None:
            continue
        if res.get("__rate_limit"):
            log(f"⚠  Rate limit en {mod.split('/')[-1]} — rotando modelo...")
            time.sleep(1.5)
            continue
        if res.get("__timeout"):
            log("⚠  Timeout — reintentando...")
            time.sleep(1)
            continue
        if "__error" in res or "__exception" in res or "__parse_error" in res:
            log(f"⚠  {list(res.values())[0]}")
            time.sleep(0.5)
            continue
        
        proximo = (idx + 1) % total
        return res, proximo
    
    log("⏭  Groq sin respuesta")
    return None, modelo_idx


def _traducir_google(img, idioma: str, log) -> tuple[dict | None, int]:
    """Traduce usando Google Vision API + Google Translate."""
    try:
        from google.cloud import vision, translate_v2
        
        client = vision.ImageAnnotatorClient()
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        image = vision.Image(content=img_bytes.getvalue())
        
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts:
            return None, 0
        
        texto_completo = texts[0].description.replace("\n", " ").strip()
        if not texto_completo:
            return None, 0
        
        translate_client = translate_v2.Client()
        idioma_map = {"español": "es", "inglés": "en", "portugués": "pt", "francés": "fr", "alemán": "de"}
        target = idioma_map.get(idioma, "es")
        
        result = translate_client.translate(texto_completo, target_language=target)
        traduccion = result["translatedText"]
        
        return {
            "idioma_detectado": "detected",
            "es_idioma_destino": False,
            "texto_completo": texto_completo,
            "traduccion_completa": traduccion,
            "bloques": [{"original": texto_completo, "traduccion": traduccion, "x_pct": 0.5, "y_pct": 0.5, "es_idioma_destino": False}]
        }, 0
    except Exception as e:
        log(f"⚠  Google error: {e}")
        return None, 0


def _traducir_deepl(img, api_key: str, idioma: str, log) -> tuple[dict | None, int]:
    """Traduce usando Tesseract OCR + DeepL API."""
    try:
        import pytesseract
        
        texto = pytesseract.image_to_string(img, lang='jpn+eng')
        texto_completo = texto.strip().replace("\n", " ")
        if not texto_completo:
            return None, 0
        
        idioma_map = {"español": "ES", "inglés": "EN", "portugués": "PT-PT", "francés": "FR", "alemán": "DE"}
        target = idioma_map.get(idioma, "ES")
        
        data = {"auth_key": api_key, "text": texto_completo, "target_lang": target}
        r = requests.post("https://api-free.deepl.com/v2/translate", data=data, timeout=10)
        
        if r.status_code != 200:
            return None, 0
        
        traduccion = r.json()["translations"][0]["text"]
        
        return {
            "idioma_detectado": "detected",
            "es_idioma_destino": False,
            "texto_completo": texto_completo,
            "traduccion_completa": traduccion,
            "bloques": [{"original": texto_completo, "traduccion": traduccion, "x_pct": 0.5, "y_pct": 0.5, "es_idioma_destino": False}]
        }, 0
    except Exception as e:
        log(f"⚠  DeepL error: {e}")
        return None, 0


def _traducir_libretranslate(img, idioma: str, log) -> tuple[dict | None, int]:
    """Traduce usando LibreTranslate API (gratuito, instancias públicas)."""
    try:
        import pytesseract
        texto = pytesseract.image_to_string(img, lang='jpn+eng+kor+chi_sim')
        texto_completo = texto.strip().replace("\n", " ")
        if not texto_completo:
            return None, 0
        
        idioma_map = {"español": "es", "inglés": "en", "portugués": "pt", "francés": "fr", "alemán": "de"}
        target = idioma_map.get(idioma, "es")
        
        r = requests.post("https://libretranslate.com/translate", json={
            "q": texto_completo,
            "source": "auto",
            "target": target,
            "format": "text"
        }, timeout=15)
        
        if r.status_code != 200:
            return None, 0
        
        traduccion = r.json().get("translatedText", "")
        return {
            "idioma_detectado": "detected",
            "es_idioma_destino": False,
            "texto_completo": texto_completo,
            "traduccion_completa": traduccion,
            "bloques": [{"original": texto_completo, "traduccion": traduccion, "x_pct": 0.5, "y_pct": 0.5, "es_idioma_destino": False}]
        }, 0
    except Exception as e:
        log(f"⚠  LibreTranslate error: {e}")
        return None, 0


def _traducir_mymemory(img, idioma: str, log) -> tuple[dict | None, int]:
    """Traduce usando MyMemory API (gratuito, 1000 palabras/dia)."""
    try:
        import pytesseract
        texto = pytesseract.image_to_string(img, lang='jpn+eng+kor+chi_sim')
        texto_completo = texto.strip().replace("\n", " ")
        if not texto_completo:
            return None, 0
        
        idioma_map = {"español": "es", "inglés": "en", "portugués": "pt", "francés": "fr", "alemán": "de"}
        target = idioma_map.get(idioma, "es")
        
        params = {"q": texto_completo, "langpair": f"auto|{target}"}
        r = requests.get("https://api.mymemory.translated.net/get", params=params, timeout=15)
        
        if r.status_code != 200:
            return None, 0
        
        data = r.json()
        traduccion = data.get("responseData", {}).get("translatedText", "")
        
        return {
            "idioma_detectado": "detected",
            "es_idioma_destino": False,
            "texto_completo": texto_completo,
            "traduccion_completa": traduccion,
            "bloques": [{"original": texto_completo, "traduccion": traduccion, "x_pct": 0.5, "y_pct": 0.5, "es_idioma_destino": False}]
        }, 0
    except Exception as e:
        log(f"⚠  MyMemory error: {e}")
        return None, 0


# ════════════════════════════════════════════════════════════════════════════
#  OVERLAY DE BURBUJAS (encima del juego, fullscreen transparente)
# ════════════════════════════════════════════════════════════════════════════
class BubbleOverlay:
    """
    Ventana tkinter transparente fullscreen always-on-top.
    Dibuja burbujas de traducción exactamente donde está el texto.
    En Windows se vuelve click-through automáticamente.
    """
    # Paleta de colores para las burbujas (varía por bloque)
    PALETA = [
        ("#1e3a5f", "#93c5fd"),   # azul
        ("#166534", "#bbf7d0"),   # verde
        ("#6441a5", "#e9d5ff"),   # púrpura
        ("#78350f", "#fcd34d"),   # ámbar
        ("#7f1d1d", "#fca5a5"),   # rojo oscuro
    ]

    def __init__(self, root: tk.Tk):
        self.root    = root
        self.win     = None
        self.canvas  = None
        self._ids    = []
        self._visible = False
        self._lock   = threading.Lock()

    def _crear_ventana(self):
        if self.win is not None:
            return
        self.win = tk.Toplevel(self.root)
        self.win.title("__overlay__")
        self.win.attributes("-topmost", True)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.0)   # invisible hasta dibujar
        self.win.overrideredirect(True)
        self.win.configure(bg="black")

        self.canvas = tk.Canvas(self.win, bg="black",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Click-through en Windows
        try:
            import ctypes
            hwnd = self.win.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED   = 0x80000
            WS_EX_TRANSPARENT = 0x20
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception:
            pass

        self.win.withdraw()

    def dibujar(self, bloques: list, bbox=None):
        """
        Dibuja burbujas en pantalla.
        bbox = (x1,y1,x2,y2) del área capturada (para escalar coordenadas).
        Si bbox=None = pantalla completa.
        """
        self.root.after(0, self._dibujar_en_hilo_ui, bloques, bbox)

    def _dibujar_en_hilo_ui(self, bloques, bbox):
        with self._lock:
            self._crear_ventana()
            self.canvas.delete("all")
            self._ids.clear()

            if not bloques:
                self.win.withdraw()
                self._visible = False
                return

            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()

            # Calcular offset y escala del área capturada
            if bbox:
                ax1, ay1, ax2, ay2 = bbox
                aw, ah = ax2 - ax1, ay2 - ay1
            else:
                ax1, ay1 = 0, 0
                aw, ah   = sw, sh

            for i, bloque in enumerate(bloques):
                trad = bloque.get("traduccion", "").strip()
                orig = bloque.get("original", "").strip()
                if not trad or trad == orig:
                    continue

                x_pct = float(bloque.get("x_pct", 0.5))
                y_pct = float(bloque.get("y_pct", 0.5))

                # Convertir porcentaje de área a coordenadas de pantalla
                cx = int(ax1 + x_pct * aw)
                cy = int(ay1 + y_pct * ah)

                # Limitar para que no salga de pantalla
                cx = max(10, min(cx, sw - 220))
                cy = max(10, min(cy, sh - 60))

                bg_color, txt_color = self.PALETA[i % len(self.PALETA)]

                # Calcular tamaño de burbuja
                chars_linea = 30
                lineas      = max(1, (len(trad) // chars_linea) + 1)
                bw          = min(len(trad) * 7 + 20, 260)
                bh          = lineas * 17 + 16

                # Triángulo indicador (apunta hacia arriba)
                self.canvas.create_polygon(
                    cx + 10, cy - 5,
                    cx + 20, cy - 5,
                    cx + 15, cy + 3,
                    fill=bg_color, outline=""
                )

                # Rectángulo de burbuja
                rx1, ry1 = cx, cy
                rx2, ry2 = cx + bw, cy + bh
                # Esquinas redondeadas simuladas con overlapping rects
                r = 6
                self.canvas.create_rectangle(rx1+r, ry1, rx2-r, ry2,
                                             fill=bg_color, outline="")
                self.canvas.create_rectangle(rx1, ry1+r, rx2, ry2-r,
                                             fill=bg_color, outline="")
                self.canvas.create_oval(rx1, ry1, rx1+r*2, ry1+r*2,
                                        fill=bg_color, outline="")
                self.canvas.create_oval(rx2-r*2, ry1, rx2, ry1+r*2,
                                        fill=bg_color, outline="")
                self.canvas.create_oval(rx1, ry2-r*2, rx1+r*2, ry2,
                                        fill=bg_color, outline="")
                self.canvas.create_oval(rx2-r*2, ry2-r*2, rx2, ry2,
                                        fill=bg_color, outline="")

                # Borde sutil
                self.canvas.create_rectangle(rx1+r, ry1, rx2-r, ry2,
                                             outline=txt_color, width=1)

                # Texto de traducción
                self.canvas.create_text(
                    cx + bw // 2,
                    cy + bh // 2,
                    text=trad,
                    fill=txt_color,
                    font=("Arial", 10, "bold"),
                    width=bw - 10,
                    anchor="center"
                )

            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.win.attributes("-alpha", 0.93)
            self._visible = True

    def limpiar(self):
        if self.win:
            self.root.after(0, self._limpiar_ui)

    def _limpiar_ui(self):
        if self.canvas:
            self.canvas.delete("all")
        if self.win:
            self.win.withdraw()
        self._visible = False


# ════════════════════════════════════════════════════════════════════════════
#  PANEL FLOTANTE (texto original + traducción)
# ════════════════════════════════════════════════════════════════════════════
class FloatingPanel:
    """Panel arrastrable always-on-top con traducciones acumuladas."""

    def __init__(self, root: tk.Tk, modo: str = MODO_DEFAULT):
        self.root = root
        self.win  = None
        self._modo = modo
        self._historial = []

    def _crear(self):
        if self.win is not None:
            return
        self.win = tk.Toplevel(self.root)
        self.win.title("Traductor VTuber")
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.geometry("560x280+20+20")
        self.win.configure(bg=C_BG)
        self.win.resizable(True, True)

        bar = tk.Frame(self.win, bg=C_BAR)
        bar.pack(fill="x")

        self._modo_lbl = tk.Label(bar, text=f"🈳 Traductor  —  {self._modo}",
                                  bg=C_BAR, fg=C_TXT,
                                  font=("Arial", 10, "bold"))
        self._modo_lbl.pack(side="left", padx=8, pady=5)

        tk.Button(bar, text="🗑️ Limpiar", bg=C_BAR, fg=C_AMB,
                  relief="flat", bd=0, font=("Arial", 10, "bold"),
                  command=self.limpiar_historial).pack(side="left", padx=4)

        tk.Button(bar, text="✕", bg=C_BAR, fg=C_RED,
                  relief="flat", bd=0, font=("Arial", 10, "bold"),
                  command=self.ocultar).pack(side="right", padx=6)

        bar.bind("<ButtonPress-1>",   self._ds)
        bar.bind("<B1-Motion>",       self._dm)

        # Área de historial con scroll
        hist_frame = tk.Frame(self.win, bg=C_BG)
        hist_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        
        self.hist_text = tk.Text(hist_frame, bg=C_LOGBG or "#0f1117", fg=C_TXT,
                                  font=("Consolas", 11), wrap="word",
                                  bd=0, highlightthickness=0, state="disabled")
        self.hist_text.pack(side="left", fill="both", expand=True)
        
        scroll = tk.Scrollbar(hist_frame, command=self.hist_text.yview)
        scroll.pack(side="right", fill="y")
        self.hist_text.config(yscrollcommand=scroll.set)

        self._dx = self._dy = 0

    def _ds(self, e): self._dx, self._dy = e.x, e.y
    def _dm(self, e):
        x = self.win.winfo_x() + e.x - self._dx
        y = self.win.winfo_y() + e.y - self._dy
        self.win.geometry(f"+{x}+{y}")

    def limpiar_historial(self):
        self._historial = []
        self.hist_text.config(state="normal")
        self.hist_text.delete("1.0", "end")
        self.hist_text.config(state="disabled")

    def set_modo(self, modo: str):
        self._modo = modo
        if self.win and self._modo_lbl:
            self._modo_lbl.configure(text=f"🈳 Traductor  —  {modo}")

    def set_texto(self, original: str, traduccion: str, es_destino: bool = False):
        self.root.after(0, self._actualizar, original, traduccion, es_destino)

    def _actualizar(self, original, traduccion, es_destino):
        self._crear()
        
        # Acumular en historial
        self._historial.append(f"📄 {original[:60]}...\n🌐 {traduccion}\n---")
        if len(self._historial) > 10:
            self._historial.pop(0)
        
        # Actualizar texto
        self.hist_text.config(state="normal")
        self.hist_text.delete("1.0", "end")
        self.hist_text.insert("end", "\n".join(self._historial))
        self.hist_text.see("end")
        self.hist_text.config(state="disabled")

        # Auto resize
        h = min(100 + len(self._historial) * 45, 400)
        x, y = self.win.winfo_x(), self.win.winfo_y()
        self.win.geometry(f"560x{h}+{x}+{y}")

    def mostrar(self):
        self.root.after(0, self._mostrar_ui)

    def _mostrar_ui(self):
        self._crear()
        self.win.deiconify()
        self.win.attributes("-topmost", True)

    def ocultar(self):
        if self.win:
            self.win.withdraw()


# ════════════════════════════════════════════════════════════════════════════
#  SELECTOR DE ÁREA (como MORT)
# ════════════════════════════════════════════════════════════════════════════
class AreaSelector:
    """Pantalla semitransparente para dibujar el área a traducir."""

    def __init__(self, callback):
        self.callback = callback

    def seleccionar(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        root = tk.Tk()
        root.withdraw()
        time.sleep(0.15)   # pequeña pausa para que el overlay previo desaparezca

        sel = tk.Toplevel(root)
        sel.attributes("-fullscreen", True)
        sel.attributes("-alpha", 0.22)
        sel.attributes("-topmost", True)
        sel.configure(bg="black")

        canvas = tk.Canvas(sel, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        tk.Label(sel,
                 text="📷  Arrastra para seleccionar el área a traducir  •  ESC para cancelar",
                 bg="black", fg="white",
                 font=("Arial", 13, "bold")).place(relx=0.5, y=22, anchor="center")

        rect_id = [None]
        start   = [0, 0]
        coords  = [None]

        def press(e):
            start[0], start[1] = e.x, e.y
        def drag(e):
            if rect_id[0]: canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(
                start[0], start[1], e.x, e.y,
                outline="#00ff99", width=2, fill="#00ff9912")
        def release(e):
            x1 = min(start[0], e.x); y1 = min(start[1], e.y)
            x2 = max(start[0], e.x); y2 = max(start[1], e.y)
            if x2 - x1 > 15 and y2 - y1 > 10:
                coords[0] = (x1, y1, x2, y2)
            sel.destroy(); root.destroy()
        def esc(e):
            sel.destroy(); root.destroy()

        canvas.bind("<ButtonPress-1>",   press)
        canvas.bind("<B1-Motion>",       drag)
        canvas.bind("<ButtonRelease-1>", release)
        sel.bind("<Escape>",             esc)
        root.mainloop()

        if coords[0]:
            self.callback(coords[0])


# ════════════════════════════════════════════════════════════════════════════
#  CONTROLADOR PRINCIPAL — TranslatorManager
# ════════════════════════════════════════════════════════════════════════════
class TranslatorManager:
    """
    Controlador principal del traductor estilo MORT.
    Puede usarse integrado en main.py o standalone.

    Parámetros:
      master        — ventana tkinter raíz (o None para crear una interna)
      api_key       — Groq API key
      speak_fn      — función speak(texto, voz, dispositivo) o None
      stop_audio_fn — función stop_audio() o None
      get_devices_fn— función que devuelve (speaker_id, ia_id) o None
      voice         — voz TTS por defecto
      idioma_destino— idioma de traducción
      log_fn        — función de log(texto) o None
      leer_en_voz   — bool, si True vocaliza la traducción
      modo          — modo de traducción inicial
    """

    def __init__(self, master=None, api_key: str = "",
                 speak_fn=None, stop_audio_fn=None, get_devices_fn=None,
                 voice: str = "es-MX-DaliaNeural",
                 idioma_destino: str = "español",
                 log_fn=None, leer_en_voz: bool = True,
                 modo: str = MODO_DEFAULT, motor: str = "Groq (OCR)"):

        self.api_key        = api_key
        self.speak          = speak_fn
        self.stop_audio     = stop_audio_fn
        self.get_devices    = get_devices_fn
        self.voice          = voice
        self.idioma_destino = idioma_destino
        self.log            = log_fn or print
        self.leer_en_voz    = leer_en_voz
        self.modo           = modo
        self.motor          = motor
        self.intervalo      = 4
        self.area_fija      = None

        self.activo         = False
        self._thread        = None
        self._modelo_idx    = 0
        self._ultimo_texto  = ""

        # Historial acumulado de traducciones
        self._historial     = []
        self._max_historial = 10  # máximo de líneas guardadas

        # Si no hay master, crear ventana raíz oculta
        self._owns_root = master is None
        if self._owns_root:
            self._root = tk.Tk()
            self._root.withdraw()
            self._root.title("VTuber Translator")
        else:
            self._root = master

        self.panel   = FloatingPanel(self._root, modo)
        self.overlay = BubbleOverlay(self._root)
        self.panel.mostrar()

        # Registrar hotkeys globales (solo si keyboard está disponible)
        self._hotkeys_activos = False
        self._registrar_hotkeys()

    def _registrar_hotkeys(self):
        try:
            import keyboard
            keyboard.add_hotkey("ctrl+t", self._hotkey_area_unica)
            keyboard.add_hotkey("ctrl+r", self._hotkey_repetir)
            keyboard.add_hotkey("ctrl+w", self._hotkey_toggle_continuo)
            self._hotkeys_activos = True
            self.log("⌨  Hotkeys: Ctrl+T = área  |  Ctrl+W = continuo  |  Ctrl+R = repetir")
        except ImportError:
            self.log("⚠  Hotkeys no disponibles — pip install keyboard")
        except Exception as e:
            self.log(f"⚠  Hotkeys error: {e}")

    # ── Hotkeys ───────────────────────────────────────────────────────────────
    def _hotkey_area_unica(self):
        self.log("⌨  Ctrl+T → seleccionando área...")
        self.seleccionar_area_y_traducir()

    def _hotkey_repetir(self):
        if self.area_fija:
            self.log("⌨  Ctrl+R → repitiendo traducción del área...")
            self.traducir_ahora(bbox=self.area_fija, con_overlay=False)
        else:
            self.log("⚠  Ctrl+R: no hay área seleccionada aún (usa Ctrl+T primero)")

    def _hotkey_toggle_continuo(self):
        if self.activo:
            self.log("⌨  Ctrl+W → deteniendo traducción continua")
            self.detener_continuo()
        else:
            if self.area_fija:
                self.log("⌨  Ctrl+W → iniciando traducción continua en área guardada...")
                self.iniciar_continuo(con_overlay=False)
            else:
                self.log("⌨  Ctrl+W → selecciona área primero (Ctrl+T)")
                self.seleccionar_area_continuo()

    # ── API pública ───────────────────────────────────────────────────────────
    def set_modo(self, modo: str):
        self.modo = modo
        self.panel.set_modo(modo)
        self.log(f"🌐  Modo: {modo}")

    def traducir_ahora(self, bbox=None, con_overlay: bool = True):
        """Traduce una sola vez."""
        threading.Thread(
            target=self._traducir_una_vez,
            args=(bbox, con_overlay),
            daemon=True
        ).start()

    def seleccionar_area_y_traducir(self):
        """Abre selector de área → traduce una vez."""
        def on_area(coords):
            self.area_fija = coords
            self.log(f"📐  Área guardada: {coords}")
            self.traducir_ahora(bbox=coords, con_overlay=False)
        AreaSelector(on_area).seleccionar()

    def seleccionar_area_continuo(self):
        """Abre selector de área → inicia traducción continua."""
        def on_area(coords):
            self.area_fija = coords
            self.log(f"📐  Área continua: {coords}")
            self.iniciar_continuo(con_overlay=False)
        AreaSelector(on_area).seleccionar()

    def traducir_pantalla_unica(self):
        """Traduce pantalla completa con overlay."""
        self.log("🖥️  Traduciendo pantalla completa...")
        self.traducir_ahora(bbox=None, con_overlay=True)

    def iniciar_pantalla_continuo(self):
        """Pantalla completa continua con overlay."""
        self.area_fija = None
        self.iniciar_continuo(con_overlay=True)

    def iniciar_continuo(self, con_overlay: bool = False):
        if self.activo:
            self.log("⚠  Ya hay traducción continua activa"); return
        self.activo  = True
        self._thread = threading.Thread(
            target=self._loop_continuo, args=(con_overlay,), daemon=True)
        self._thread.start()
        self.log(f"▶  Traducción continua (cada {self.intervalo}s) {'con overlay' if con_overlay else 'en panel'}")

    def detener_continuo(self):
        self.activo = False
        self.overlay.limpiar()
        self.log("⏹  Traducción continua detenida")

    # ── Interno ───────────────────────────────────────────────────────────────
    def _loop_continuo(self, con_overlay: bool):
        while self.activo:
            self._traducir_una_vez(self.area_fija, con_overlay)
            for _ in range(self.intervalo):
                if not self.activo: break
                time.sleep(1)

    def _traducir_una_vez(self, bbox=None, con_overlay: bool = True):
        if not PIL_OK:
            self.log("❌  Falta pillow — pip install pillow"); return
        if not self.api_key or not self.api_key.strip():
            self.log("❌  Falta GROQ_API_KEY"); return
        try:
            # Ocultar el panel flotante durante la captura para no OCRearlo
            self.panel.ocultar()
            time.sleep(0.1)
            
            region = bbox or self.area_fija
            self.log("📸  Capturando...")
            img = ImageGrab.grab(bbox=region)
            
            # Restaurar panel
            self.panel.mostrar()
            
            self.log(f"🧠  OCR+traducción [{self.motor}]...")
            resultado, nuevo_idx = traducir_imagen(
                img, self.api_key, self.modo,
                self.idioma_destino, self._modelo_idx, self.log, self.motor)
            self._modelo_idx = nuevo_idx

            if not resultado:
                return

            self._procesar(resultado, bbox or region, con_overlay)

        except Exception as e:
            self.log(f"❌  Error: {e}")
            self.log(traceback.format_exc())

    def _procesar(self, resultado: dict, bbox, con_overlay: bool):
        original   = resultado.get("texto_completo", "").strip()
        traduccion = resultado.get("traduccion_completa", original).strip()
        bloques    = resultado.get("bloques", [])
        es_destino = resultado.get("es_idioma_destino", False)
        idioma     = resultado.get("idioma_detectado", "?")

        if not original:
            self.log("⏭  Sin texto detectado")
            return
        if traduccion == self._ultimo_texto:
            self.log("⏭  Texto sin cambios")
            return
        self._ultimo_texto = traduccion

        # Log
        if es_destino:
            self.log(f"🔊  [{idioma}] Texto en {self.idioma_destino} — leyendo como narrador")
        else:
            preview = traduccion[:70] + ("..." if len(traduccion) > 70 else "")
            self.log(f"🌐  [{idioma}→{self.idioma_destino}] {preview}")

        # Panel flotante
        self.panel.set_texto(original, traduccion, es_destino)
        self.panel.mostrar()

        # Overlay de burbujas
        if con_overlay and bloques:
            self.overlay.dibujar(bloques, bbox)
        elif not con_overlay:
            self.overlay.limpiar()

        # TTS continuo sin interrumpir
        if self.leer_en_voz:
            texto_voz = original if es_destino else traduccion
            if texto_voz.strip() and self.speak:
                try:
                    _, ia_dev = self.get_devices() if self.get_devices else (0, 0)
                    self.speak(texto_voz, self.voice, ia_dev)
                except Exception as e:
                    self.log(f"⚠  Voz error: {e}")

    def cerrar(self):
        self.detener_continuo()
        try:
            if self._hotkeys_activos:
                import keyboard
                keyboard.remove_hotkey("ctrl+t")
                keyboard.remove_hotkey("ctrl+r")
                keyboard.remove_hotkey("ctrl+w")
        except Exception:
            pass

    def mainloop(self):
        """Solo para modo standalone."""
        if self._owns_root:
            self._root.mainloop()


# ════════════════════════════════════════════════════════════════════════════
#  MODO STANDALONE — ejecutar solo: python translator.py
# ════════════════════════════════════════════════════════════════════════════
def _standalone():
    cfg     = _leer_config()
    api_key = cfg.get("GROQ_API_KEY", "").strip()

    if not api_key:
        api_key = input("🔑 Pega tu GROQ_API_KEY: ").strip()

    print("\n🈳  VTuber Traductor estilo MORT")
    print("─────────────────────────────────")
    print("⌨  Ctrl+T  → Seleccionar área y traducir")
    print("⌨  Ctrl+R  → Repetir última área")
    print("⌨  Ctrl+W  → Activar/Desactivar traducción continua")
    print("⌨  Ctrl+C  → Salir")
    print("─────────────────────────────────\n")

    # Intentar cargar TTS (edge-tts vía src.audio si existe)
    speak_fn = None
    stop_fn  = None
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.audio import speak as _spk, stop_audio as _stop
        speak_fn = _spk
        stop_fn  = _stop
        print("✅  TTS cargado desde src.audio")
    except Exception:
        print("⚠  TTS no disponible en modo standalone")

    translator = TranslatorManager(
        master         = None,
        api_key        = api_key,
        speak_fn       = speak_fn,
        stop_audio_fn  = stop_fn,
        get_devices_fn = None,
        voice          = "es-MX-DaliaNeural",
        idioma_destino = "español",
        leer_en_voz    = speak_fn is not None,
        modo           = MODO_DEFAULT,
    )

    try:
        translator.mainloop()
    except KeyboardInterrupt:
        translator.cerrar()
        print("\n👋 Traductor cerrado")


if __name__ == "__main__":
    _standalone()
