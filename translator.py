import threading
import time
import base64
import io
import tkinter as tk
import requests
from PIL import ImageGrab, Image, ImageTk
import traceback


# =====================================================================
#  VENTANA FLOTANTE (siempre encima del juego)
# =====================================================================
class FloatingTranslator(tk.Toplevel):
    """Ventana transparente always-on-top que muestra la traducción."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Traductor")
        self.attributes("-topmost", True)          # siempre encima
        self.attributes("-alpha", 0.92)            # ligera transparencia
        self.overrideredirect(False)               # mantener barra para mover
        self.geometry("520x160+20+20")
        self.configure(bg="#1a1a2e")
        self.resizable(True, True)

        # Encabezado arrastrable
        header = tk.Frame(self, bg="#16213e", cursor="fleur")
        header.pack(fill="x")
        tk.Label(header, text="🈳 Traductor en tiempo real",
                 bg="#16213e", fg="#e2e2e2",
                 font=("Arial", 10, "bold")).pack(side="left", padx=8, pady=4)
        tk.Button(header, text="✕", bg="#16213e", fg="#ff6b6b",
                  relief="flat", command=self.hide,
                  font=("Arial", 10, "bold")).pack(side="right", padx=6)

        header.bind("<ButtonPress-1>",   self._drag_start)
        header.bind("<B1-Motion>",       self._drag_motion)

        # Texto original (pequeño, gris)
        self.lbl_original = tk.Label(
            self, text="", bg="#1a1a2e", fg="#888888",
            font=("Arial", 9), wraplength=500, justify="left", anchor="w")
        self.lbl_original.pack(fill="x", padx=10, pady=(4, 0))

        # Traducción (grande, blanco)
        self.lbl_traduccion = tk.Label(
            self, text="Listo para traducir...",
            bg="#1a1a2e", fg="#ffffff",
            font=("Arial", 13, "bold"), wraplength=500,
            justify="left", anchor="w")
        self.lbl_traduccion.pack(fill="both", expand=True, padx=10, pady=(2, 8))

        self._drag_x = 0
        self._drag_y = 0

    def _drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _drag_motion(self, e):
        x = self.winfo_x() + e.x - self._drag_x
        y = self.winfo_y() + e.y - self._drag_y
        self.geometry(f"+{x}+{y}")

    def set_text(self, original: str, traduccion: str):
        """Actualiza el texto desde cualquier hilo."""
        self.after(0, self._update_ui, original, traduccion)

    def _update_ui(self, original, traduccion):
        orig_corto = original[:120] + "..." if len(original) > 120 else original
        self.lbl_original.config(text=f"📄 {orig_corto}")
        self.lbl_traduccion.config(text=f"🌐 {traduccion}")
        # Auto-ajustar alto según texto
        lines = max(2, len(traduccion) // 45 + 1)
        h = 80 + lines * 22
        self.geometry(f"520x{min(h, 260)}+{self.winfo_x()}+{self.winfo_y()}")

    def hide(self):
        self.withdraw()

    def show(self):
        self.deiconify()
        self.attributes("-topmost", True)


# =====================================================================
#  SELECTOR DE ÁREA (dibuja rectángulo encima de la pantalla)
# =====================================================================
class AreaSelector:
    """Pantalla semitransparente para que el usuario dibuje el área."""

    def __init__(self, callback):
        self.callback = callback  # recibe (x1, y1, x2, y2)

    def seleccionar(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-alpha", 0.25)
        root.attributes("-topmost", True)
        root.configure(bg="black")
        root.title("Selecciona área")

        canvas = tk.Canvas(root, cursor="cross", bg="black",
                           highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        tk.Label(root,
                 text="Arrastra para seleccionar el área a traducir  •  ESC para cancelar",
                 bg="black", fg="white", font=("Arial", 13)).place(relx=0.5, y=18, anchor="center")

        rect_id = [None]
        start   = [0, 0]
        coords  = [None]

        def on_press(e):
            start[0], start[1] = e.x, e.y
            if rect_id[0]:
                canvas.delete(rect_id[0])

        def on_drag(e):
            if rect_id[0]:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(
                start[0], start[1], e.x, e.y,
                outline="#00ff99", width=2, fill="#00ff9920")

        def on_release(e):
            x1 = min(start[0], e.x)
            y1 = min(start[1], e.y)
            x2 = max(start[0], e.x)
            y2 = max(start[1], e.y)
            coords[0] = (x1, y1, x2, y2)
            root.destroy()

        def on_esc(e):
            root.destroy()

        canvas.bind("<ButtonPress-1>",   on_press)
        canvas.bind("<B1-Motion>",       on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind("<Escape>",            on_esc)
        root.mainloop()

        if coords[0] and self.callback:
            self.callback(coords[0])


# =====================================================================
#  MOTOR DE TRADUCCIÓN (OCR + Groq)
# =====================================================================
def imagen_a_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def traducir_con_groq(img_b64: str, api_key: str, idioma_destino: str = "español") -> dict:
    """
    Usa Groq vision para OCR + traducción en un solo paso.
    Devuelve {"original": ..., "traduccion": ...}
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    sistema = (
        f"Eres un traductor experto. El usuario te mandará una imagen de un juego. "
        f"Tu tarea es:\n"
        f"1. Leer TODO el texto visible en la imagen (japonés, chino, coreano, inglés, etc.)\n"
        f"2. Traducir ese texto al {idioma_destino}.\n"
        f"Responde ÚNICAMENTE en este formato JSON exacto sin markdown:\n"
        f'{{ "original": "texto original aquí", "traduccion": "traducción aquí" }}\n'
        f"Si no hay texto visible responde: "
        f'{{ "original": "", "traduccion": "Sin texto detectado" }}'
    )
    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": "Traduce el texto de esta imagen."}
            ]}
        ],
        "max_tokens": 400,
        "temperature": 0.1
    }
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=data, headers=headers, timeout=25
    )
    if r.status_code != 200:
        return {"original": "", "traduccion": f"Error API ({r.status_code})"}

    content = r.json()["choices"][0]["message"]["content"].strip()

    # Parsear JSON de forma segura
    import json, re
    try:
        # Limpiar posibles bloques markdown
        content = re.sub(r"```json|```", "", content).strip()
        resultado = json.loads(content)
        return resultado
    except Exception:
        return {"original": content, "traduccion": content}


# =====================================================================
#  CONTROLADOR PRINCIPAL
# =====================================================================
class TranslatorManager:
    """
    Gestiona el traductor: modo continuo (pantalla completa) y
    modo manual (área seleccionada).
    """

    def __init__(self, master, api_key: str, speak_fn, stop_audio_fn,
                 get_devices_fn, voice: str = "es-MX-DaliaNeural",
                 idioma_destino: str = "español", log_fn=None,
                 leer_en_voz: bool = True):

        self.api_key       = api_key
        self.speak         = speak_fn
        self.stop_audio    = stop_audio_fn
        self.get_devices   = get_devices_fn
        self.voice         = voice
        self.idioma_destino = idioma_destino
        self.log           = log_fn or print
        self.leer_en_voz   = leer_en_voz

        # Ventana flotante
        self.ventana = FloatingTranslator(master)
        self.ventana.show()

        # Estado
        self.activo         = False
        self.area_fija      = None   # (x1,y1,x2,y2) o None = pantalla completa
        self.intervalo      = 4      # segundos entre capturas en modo continuo
        self._thread        = None
        self._ultimo_texto  = ""     # evita repetir traducción igual

    # ------------------------------------------------------------------
    def traducir_ahora(self, bbox=None):
        """Traduce una sola vez (área dada o pantalla completa)."""
        threading.Thread(target=self._traducir_una_vez,
                         args=(bbox,), daemon=True).start()

    def _traducir_una_vez(self, bbox=None):
        try:
            region = bbox or self.area_fija
            img = ImageGrab.grab(bbox=region)
            img_b64 = imagen_a_base64(img)
            resultado = traducir_con_groq(img_b64, self.api_key, self.idioma_destino)
            original   = resultado.get("original", "")
            traduccion = resultado.get("traduccion", "")

            if not traduccion or traduccion == self._ultimo_texto:
                return

            self._ultimo_texto = traduccion
            self.ventana.set_text(original, traduccion)
            self.log(f"🈳 [{self.idioma_destino}] {traduccion}")

            if self.leer_en_voz and traduccion and traduccion != "Sin texto detectado":
                self.stop_audio()
                _, ia_dev = self.get_devices()
                self.speak(traduccion, self.voice, ia_dev)

        except Exception as e:
            self.log(f"❌ Error traducción: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    def seleccionar_area_y_traducir(self):
        """Abre el selector de área y traduce una vez."""
        self.ventana.show()
        def on_area(coords):
            self.area_fija = coords
            self.log(f"📐 Área: {coords}")
            self.traducir_ahora(coords)
        AreaSelector(on_area).seleccionar()

    def seleccionar_area_continuo(self):
        """Abre el selector y luego inicia modo continuo en esa área."""
        def on_area(coords):
            self.area_fija = coords
            self.log(f"📐 Área fija continua: {coords}")
            self.iniciar_continuo()
        AreaSelector(on_area).seleccionar()

    # ------------------------------------------------------------------
    def iniciar_continuo(self):
        """Inicia la traducción automática cada N segundos."""
        if self.activo:
            return
        self.activo = True
        self.ventana.show()
        self._thread = threading.Thread(target=self._loop_continuo, daemon=True)
        self._thread.start()
        self.log(f"▶ Traducción continua iniciada (cada {self.intervalo}s)")

    def detener_continuo(self):
        self.activo = False
        self.log("⏹ Traducción continua detenida")

    def _loop_continuo(self):
        while self.activo:
            self._traducir_una_vez(self.area_fija)
            time.sleep(self.intervalo)
