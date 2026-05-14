"""
game_watcher.py — Comentarista de juego en tiempo real + Lector de subtítulos
"""
import threading, time, traceback, random, os, re, base64, io, gc

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

import cv2
import numpy as np

try:
    import easyocr
    EASYOCR_OK = True
    _easyocr_reader = None
except ImportError:
    EASYOCR_OK = False
    _easyocr_reader = None

WIN_CAPTURE_OK = True
from src.utils.win_capture import capturar_para_hash, capturar_pantalla
from src.utils.vision import detectar_movimiento, sistema_reglas, detectar_colores_hsv, background_subtractor_iniciar, background_subtractor_aplicar




def _detectar_color_dominante_simple(img):
    """Detección rápida de colores predominantes (sin HSV, solo RGB básico)"""
    arr = np.array(img.resize((32, 24), Image.BILINEAR))
    r, g, b = arr[..., 0].mean(), arr[..., 1].mean(), arr[..., 2].mean()
    if r > 150 and g < 100 and b < 100:
        return "rojo"
    if r > 150 and g > 120 and b < 80:
        return "naranja"
    if r > 150 and g > 150 and b < 80:
        return "amarillo"
    if r < 80 and g > 120 and b < 80:
        return "verde"
    if r < 80 and g < 80 and b > 120:
        return "azul"
    if r > 120 and g < 80 and b > 120:
        return "morado"
    if r < 60 and g < 60 and b < 60:
        return "oscuro"
    if r > 180 and g > 180 and b > 180:
        return "claro"
    return "neutro"


_COMENTARIOS_POR_COLOR = {
    "rojo": "¡Hay mucho rojo! Esto parece peligroso.",
    "naranja": "Alerta naranja, algo se acerca.",
    "verde": "Todo tranquilo por ahora, zona segura.",
    "azul": "Se ve un ambiente calmado, azul predominante.",
    "oscuro": "Está bastante oscuro, ¿es de noche o es un lugar cerrado?",
    "claro": "Hay mucha luz, se ve todo bien.",
}

_COMENTARIOS_JUEGO = [
    "Qué jugadorazo, así se hace.",
    "Uy, eso no fue buena idea.",
    "Vamos, tú puedes.",
    "Qué buena jugada.",
    "Casi, casi, la próxima.",
    "Eso fue limpio, muy limpio.",
    "Mira quién está dando cátedra.",
    "Buf, eso dolió.",
    "Qué manera de hacerlo.",
    "Demasiado fácil para ti, ¿eh?",
]


def _init_easyocr_bg():
    global _easyocr_reader
    try:
        _easyocr_reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
    except:
        pass


class GameWatcher:
    """Comentarista de juego - captura pantalla y comenta"""
    
    def __init__(self, speak_fn, stop_audio_fn, get_devices_fn, log_fn=None):
        self.speak = speak_fn
        self.stop_audio = stop_audio_fn
        self.get_devices = get_devices_fn
        self.log = log_fn or print
        
        self._running = False
        self._thread = None
        self._ultimo_hash = ""
        self._ultimo_comentario = ""
        self._comentarios_vistos = set()
        self.voice = "es-MX-DaliaNeural"
        self.juego_actual = "juego"
        self._modo = ""
        self._groq_key = ""
        self._easyocr_ready = False
    
    def _cargar_prompt(self):
        ruta_prompt = os.path.join("prompts", "default.txt")
        try:
            cfg_path = os.path.join("config", "config.txt")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            if k.strip() == "SELECTED_PROMPT":
                                seleccionado = v.strip()
                                ruta = os.path.join("prompts", seleccionado)
                                if os.path.exists(ruta):
                                    ruta_prompt = ruta
                                break
            with open(ruta_prompt, "r", encoding="utf-8") as f:
                return f.read().strip()
        except:
            return "Eres una VTuber divertida que comenta juegos con energía."
    
    def iniciar(self, voz="es-MX-DaliaNeural", juego="juego", modo="OpenCV + OCR + IA", groq_key="", solo_lectura=False):
        if self._running:
            self.log("⚠️ Ya está corriendo")
            return
        self._running = True
        self.voice = voz
        self.juego_actual = juego
        self._modo = modo
        self._groq_key = groq_key
        self._prompt = self._cargar_prompt()
        self._solo_lectura = solo_lectura
        self._easyocr_disabled = False
        try:
            cfg_path = os.path.join("config", "config.txt")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "EASYOCR_DISABLED" in line and "=1" in line:
                            self._easyocr_disabled = True
                            break
        except:
            pass
        
        background_subtractor_iniciar()
        if EASYOCR_OK and _easyocr_reader is None and not self._easyocr_disabled:
            threading.Thread(target=_init_easyocr_bg, daemon=True).start()
        

        
        if EASYOCR_OK and _easyocr_reader is None:
            threading.Thread(target=self._init_easyocr, daemon=True).start()
        
        target = self._loop_groq if "Groq" in modo else self._loop
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        self.log(f"🔴 Comentarista iniciado ({modo})")
    
    def _init_easyocr(self):
        global _easyocr_reader
        try:
            _easyocr_reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
            self._easyocr_ready = True
        except Exception as e:
            self.log(f"⚠️ EasyOCR: {e}")
    
    def detener(self):
        self._running = False
        self.log("⏹ Comentarista detenido")
    
    def _loop_groq(self):
        """Modo Groq Vision — envía captura a la API de Groq"""
        import base64, io
        from src.ai.ia import ask_vision
        intervalo = 10
        while self._running:
            try:
                img = capturar_pantalla()
                if img is None:
                    time.sleep(intervalo)
                    continue
                
                img_hash = str(hash(img.tobytes()[:300]))
                if img_hash == self._ultimo_hash:
                    time.sleep(intervalo)
                    continue
                self._ultimo_hash = img_hash
                
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=60)
                img_b64 = base64.b64encode(buf.getvalue()).decode()
                
                prompt = f"{self._prompt}\n\nDescribe brevemente qué está pasando en este juego ({self.juego_actual}). Máximo 200 caracteres."
                respuesta, _, _ = ask_vision(img_b64, prompt, self._groq_key)
                
                clave = respuesta.strip().lower()[:80]
                if respuesta and clave not in self._comentarios_vistos:
                    if len(self._comentarios_vistos) > 50:
                        self._comentarios_vistos.pop()
                    self._comentarios_vistos.add(clave)
                    self.log(f"🎮 {respuesta}")
                    _, ia_dev = self.get_devices()
                    if ia_dev is not None and ia_dev != -1:
                        self.speak(respuesta, self.voice, ia_dev)
                
                time.sleep(intervalo)
            except Exception as e:
                self.log(f"❌ Groq error: {e}")
                time.sleep(intervalo)
    
    def _loop(self):
        intervalo = 5
        frame_anterior = None
        ultimo_ocr = 0
        cooldown_ocr = 10
        
        while self._running:
            try:
                img = capturar_pantalla()
                if img is None:
                    time.sleep(intervalo)
                    continue

                arr = np.array(img.convert("RGB"))
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                ahora = time.time()
                
                # OCR: solo si pasó el cooldown
                texto_detectado = ""
                if ahora - ultimo_ocr >= cooldown_ocr:
                    texto_detectado = self._ocr_rapido(img)
                    ultimo_ocr = ahora
                    if texto_detectado:
                        self.log(f"📝 OCR: {texto_detectado[:80]}")
                
                # Modo Solo Lectura: solo OCR, sin análisis
                if self._solo_lectura:
                    if texto_detectado:
                        self._hablar(texto_detectado)
                    time.sleep(intervalo)
                    gc.collect()
                    continue
                
                # 2. Motion Detection
                movimiento = detectar_movimiento(arr, frame_anterior)
                hubo_cambio = movimiento["hay"] or frame_anterior is None
                frame_anterior = arr
                
                if not hubo_cambio and not texto_detectado:
                    time.sleep(intervalo)
                    continue
                
                # 3. Background + Color (solo si hay cambio)
                bg_mask = background_subtractor_aplicar(gray) if hubo_cambio else None
                colores_hsv = detectar_colores_hsv(arr) if hubo_cambio else None
                color_dom = _detectar_color_dominante_simple(img)
                
                # 4. Comentario
                if self._groq_key and "IA" in self._modo:
                    comentario = self._comentar_con_ia(texto_detectado, movimiento, color_dom)
                elif texto_detectado:
                    comentario = texto_detectado
                else:
                    comentario = sistema_reglas(texto_detectado, [], movimiento, color_dom, colores_hsv, None, bg_mask)
                
                if comentario:
                    self._hablar(comentario)
                
                time.sleep(intervalo)
                gc.collect()
                
            except Exception as e:
                self.log(f"❌ Error: {e}")
                time.sleep(intervalo)
    
    def _hablar(self, texto):
        clave = texto.strip().lower()[:120]
        if clave not in self._comentarios_vistos:
            if len(self._comentarios_vistos) > 50:
                self._comentarios_vistos.pop()
            self._comentarios_vistos.add(clave)
            self.log(f"🎮 {texto}")
            _, ia_dev = self.get_devices()
            if ia_dev is not None and ia_dev != -1:
                self.speak(texto, self.voice, ia_dev)

    def _ocr_rapido(self, img):
        """OCR: EasyOCR > RapidOCR > Windows OCR"""
        arr = np.array(img.convert("RGB"))

        if _easyocr_reader is not None and not self._easyocr_disabled:
            try:
                res = _easyocr_reader.readtext(arr)
                pals = [t for _, t, c in res if c > 0.5 and len(t.strip()) > 2]
                if pals:
                    texto = " ".join(pals)
                    if _es_texto_espanol(texto):
                        return texto
            except:
                pass

        try:
            from src.utils.windows_ocr import reconocer_texto
            from PIL import Image
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            texto, status = reconocer_texto(Image.fromarray(clahe.apply(gray)))
            if texto and status == "ok" and len(texto.strip()) > 3 and _es_texto_espanol(texto):
                return texto.strip()
        except:
            pass
        return ""

    def _comentar_con_ia(self, texto, movimiento, color_dom):
        """Genera comentario usando Cerebras + prompt de personalidad"""
        from src.ai.ia import ask_cerebras
        ctx = f"Juego: {self.juego_actual}. "
        if texto:
            ctx += f'Texto en pantalla: "{texto[:120]}". '
        mov_int = movimiento.get("intensidad", 0)
        if mov_int > 5:
            ctx += "Hay movimiento en pantalla. "
        ctx += f"Color predominante: {color_dom}. "
        ctx += "Comenta como una companera de juego en maximo 200 caracteres."
        try:
            resp = ask_cerebras(ctx, self._groq_key, self._prompt, max_caracteres=200)
            if resp and len(resp) > 3:
                return resp
        except:
            pass
        return None

    def _generar_comentario(self, texto, color, ciclo, escena=None, objetos=None):
        nombres = [o["nombre"] for o in (objetos or [])]
        
        if not texto and not nombres:
            if escena:
                msg = generar_comentario(escena)
                if msg:
                    return msg
            return _COMENTARIOS_POR_COLOR.get(color) or None
        
        if texto:
            if re.search(r"muerte|morir|game over|perdiste|fallaste", texto.lower()):
                return "¡Oh no! Eso no pintaba bien... ánimo."
            if re.search(r"victoria|ganaste|completado|logro|trophy|achievement", texto.lower()):
                return "¡Bien hecho! Eso se llama maestría."
            if re.search(r"peligro|enemigo|boss|jefe|cuidado", texto.lower()):
                return "¡Ojo ahí! Algo se acerca..."
            if re.search(r"pausa|menú|opciones|configuración", texto.lower()):
                return "Menú en pausa. Respira un momento."
            if re.search(r"cargando|loading", texto.lower()):
                return "Cargando... paciencia."
        
        if nombres:
            if "persona" in nombres:
                return "Veo a alguien ahí."
            if "monitor" in nombres or "laptop" in nombres:
                return "Frente al monitor."
            if "teléfono" in nombres or "telefono" in nombres:
                return "Revisando el teléfono."
            if "teclado" in nombres:
                return "Teclado activo."
            if "control" in nombres:
                return "Control en mano."
            if "silla" in nombres or "sofá" in nombres or "sofa" in nombres:
                return "Cómodamente sentado."
            vistos = list(set(nombres[:3]))
            return f"Veo {', '.join(vistos)}."
        
        if escena and escena != "explorando":
            msg = generar_comentario(escena)
            if msg:
                return msg
        
        return None


_PALABRAS_ES = {
    "el", "la", "los", "las", "un", "una", "unas", "unos", "de", "del", "en", "con",
    "por", "para", "que", "es", "son", "está", "están", "estoy", "estamos", "hay",
    "yo", "tú", "él", "ella", "usted", "nosotros", "ellos", "como", "pero",
    "porque", "cuando", "donde", "qué", "quién", "cómo", "si", "sí", "no",
    "ahora", "antes", "después", "siempre", "nunca", "todo", "nada", "algo",
    "va", "vas", "vamos", "van", "bueno", "bien", "mal", "hola", "gracias",
    "odio", "amor", "vida", "solo", "sino", "aquí", "allí", "hacer", "tener",
    "puede", "puedo", "viene", "nadie", "atención", "cuidado", "mira", "oye",
    "escucha", "dime", "muy", "más", "menos", "también", "entre", "sobre",
    "hasta", "desde", "según", "contra", "durante", "mediante", "eres", "sea",
    "sean", "fue", "era", "sido", "he", "has", "ha", "hemos", "han", "estaba",
    "estaban", "estado", "tenía", "tenían", "tenido", "dijo", "dice", "decir",
    "hace", "hacía", "hacer", "hecho", "ver", "vez", "veces", "tiempo", "forma",
    "parte", "lugar", "cosa", "cosas", "casa", "mundo", "día", "días", "año",
    "años", "hombre", "mujer", "amigo", "gente", "familia", "guerra", "paz",
    "trabajo", "dinero", "agua", "fuego", "tierra", "cielo", "noche",
    "sol", "luna", "estrella", "fuerza", "poder", "morir", "vivir", "hablar",
    "comer", "beber", "dormir", "correr", "saltar", "jugar", "ganar", "perder",
    "buscar", "encontrar", "saber", "conocer", "pensar", "creer", "entender",
    "salir", "entrar", "volver", "llegar", "pasar", "mirar", "esperar", "dejar",
    "abrir", "cerrar", "subir", "bajar", "quedar", "necesitar", "parecer",
    "suelo", "suele", "suelen", "propio", "cada", "cual", "cualquier",
    "don", "doña", "señor", "señora", "doctor", "capitán", "general",
    "adiós", "disculpa", "perdón",
    "claro", "vale", "ok", "listo", "visto", "hecho", "dicho",
    "entonces", "además", "incluso", "finalmente", "pronto", "tarde",
    "temprano", "cerca", "lejos", "dentro", "fuera", "arriba", "abajo",
    "delante", "detrás", "encima", "debajo", "alrededor", "jamás",
    "alguien", "ninguno", "varios", "demasiado", "bastante", "poco",
    "mucho", "tanto", "tan", "igual", "diferente", "mismo",
    # Palabras comunes en subtítulos de juegos
    "presiona", "pulsa", "tecla", "teclas", "botón", "boton",
    "continuar", "empezar", "comenzar", "iniciar", "reiniciar",
    "saltar", "brincar", "correr", "caminar", "nadar", "volar",
    "disparar", "atacar", "defender", "bloquear", "esquivar",
    "recoger", "soltar", "lanzar", "agarrar", "empujar", "tirar",
    "abrir", "cerrar", "usar", "tomar", "dejar", "colocar",
    "hablar", "conversar", "preguntar", "responder", "contestar",
    "comprar", "vender", "intercambiar", "mejorar", "reparar",
    "moriste", "muerto", "morir", "salvar", "guardar", "cargar",
    "aventura", "historia", "capítulo", "capitulo", "nivel", "niveles",
    "misión", "mision", "misiones", "objetivo", "meta", "prueba",
    "enemigo", "enemigos", "jefe", "boss", "monstruo", "demonio",
    "arma", "armas", "escudo", "espada", "hacha", "arco", "flecha",
    "poción", "pocion", "pociones", "tesoro", "cofre", "llave",
    "puerta", "ventana", "pasillo", "habitación", "habitacion",
    "mapa", "brújula", "brujula", "linterna", "antorcha",
    "vida", "salud", "mana", "energía", "energia", "experiencia",
    "puntos", "puntuación", "puntuacion", "récord", "record",
    "jugador", "jugadora", "personaje", "protagonista", "héroe", "heroe",
    "aliado", "aliada", "compañero", "compañera", "companero",
    "victoria", "derrota", "completado", "superado", "logro",
    "pausa", "continuar", "reanudar", "opciones", "ajustes",
    "configuración", "configuracion", "controles", "idioma",
    "volumen", "sonido", "música", "musica", "efectos",
    "pantalla", "brillo", "resolución", "resolucion", "ventana",
    "créditos", "creditos", "gracias por jugar", "the end", "fin",
}

_LIMPIAR_RE = re.compile(r'[^a-záéíóúüñ\s]')


def _es_texto_espanol(texto):
    """Determina si un texto es español analizando palabras comunes"""
    texto_limpio = _LIMPIAR_RE.sub(' ', texto.lower())
    palabras = [p for p in texto_limpio.split() if len(p) > 1]
    if not palabras:
        return False
    cantidad_es = sum(1 for p in palabras if p in _PALABRAS_ES)
    if cantidad_es >= 1:
        return True
    if any(p.endswith(("ar", "er", "ir", "ado", "ido", "ando", "endo", "ción", "sión",
                       "mente", "dad", "tad", "anza", "encia", "eza")) for p in palabras):
        return True
    return False


