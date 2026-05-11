"""
game_watcher.py — Comentarista de juego en tiempo real
Usa Windows Graphics Capture API + PaddleOCR + traducción automática
"""
import threading, time, base64, io, traceback, requests, hashlib

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

# Usar Windows Graphics Capture API
try:
    from src.utils.win_capture import capturar_para_hash, capturar_pantalla
    WIN_CAPTURE_OK = True
except ImportError:
    WIN_CAPTURE_OK = False
    print("[WARNING] win_capture no disponible, usando fallback")


def _capturar_base64(bbox=None):
    """Captura pantalla y retorna base64 para análisis"""
    if WIN_CAPTURE_OK:
        img = capturar_pantalla(bbox)
    else:
        # Fallback a PIL
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=bbox)
        except:
            return None
    
    if img is None:
        return None
    
    img = img.resize((1280, 720))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _capturar_hash(bbox=None):
    """Captura pantalla y retorna hash para detectar cambios"""
    if WIN_CAPTURE_OK:
        img, img_hash = capturar_para_hash(bbox)
        return img_hash if img_hash else ""
    else:
        # Fallback
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=bbox)
            img = img.resize((640, 360))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=50)
            return hashlib.md5(buf.getvalue()).hexdigest()
        except:
            return ""


def _traducir_texto_simple(texto, idioma_destino="es"):
    """Traduce texto usando Google Translate (gratis)"""
    if not texto:
        print("[WARNING] _traducir_texto_simple: texto vacio")
        return ""
    try:
        # Solo mostrar preview ASCII para evitar errores de encoding
        preview = texto[:20] if all(ord(c) < 128 for c in texto[:20]) else "[non-ASCII]"
        print(f"[DEBUG] Traduciendo: {preview}...")
        
        idioma_map = {
            "español": "es", "ingles": "en", "portugues": "pt",
            "frances": "fr", "aleman": "de", "japones": "ja",
            "coreano": "ko", "chino": "zh-CN"
        }
        target = idioma_map.get(idioma_destino, "es")
        
        # Detectar si el texto contiene caracteres no-latinos
        tiene_no_ascii = any(ord(c) > 127 for c in texto)
        
        # Usar auto-detect primero
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target,
            "dt": "t",
            "q": texto[:500]
        }
        r = requests.get(url, params=params, timeout=10)
        
        traduccion = ""
        if r.status_code == 200:
            result = r.json()
            if result and result[0]:
                traduccion = "".join([x[0] for x in result[0] if x[0]])
        
        # Si no tradujo (mismo texto), reintentar con diferentes fuentes
        if traduccion == texto[:len(traduccion)] and traduccion and tiene_no_ascii:
            # Probar con japones
            params["sl"] = "ja"
            r2 = requests.get(url, params=params, timeout=10)
            if r2.status_code == 200:
                result2 = r2.json()
                if result2 and result2[0]:
                    traduccion = "".join([x[0] for x in result2[0] if x[0]])
            
            # Si sigue igual, probar con coreano
            if traduccion == texto[:len(traduccion)]:
                params["sl"] = "ko"
                r3 = requests.get(url, params=params, timeout=10)
                if r3.status_code == 200:
                    result3 = r3.json()
                    if result3 and result3[0]:
                        traduccion = "".join([x[0] for x in result3[0] if x[0]])
            
            # Si sigue igual, probar con chino
            if traduccion == texto[:len(traduccion)]:
                params["sl"] = "zh-CN"
                r4 = requests.get(url, params=params, timeout=10)
                if r4.status_code == 200:
                    result4 = r4.json()
                    if result4 and result4[0]:
                        traduccion = "".join([x[0] for x in result4[0] if x[0]])
        
        preview_trad = traduccion[:20] if traduccion and all(ord(c) < 128 for c in traduccion[:20]) else "[traducido]"
        print(f"[DEBUG] Traduccion: {preview_trad}...")
        return traduccion
        
    except Exception as e:
        print(f"[ERROR] Traduccion error: {e}")
        return ""


def _analizar_con_paddle(img):
    """
    Analiza la pantalla con EasyOCR y traduce el texto.
    Genera un comentario simple basado en el texto encontrado.
    """
    try:
        # Importar EasyOCR
        from src.utils.windows_ocr import reconocer_texto_con_posicion, reconocer_texto
        
        # Primero probar reconocimiento simple
        img_captura = capturar_pantalla() if img is None else img
        if img_captura is None:
            return "Error capturando pantalla", "error"
        
        print("[DEBUG] Ejecutando OCR...")
        texto, estado = reconocer_texto(img_captura)
        
        if not texto or estado != "success":
            return "No se detectó texto", "no_text"
        
        print(f"[DEBUG] Texto detectado: {texto[:50]}...")
        
        # Traducir al español
        print("[DEBUG] Traduciendo...")
        traduccion = _traducir_texto_simple(texto, "es")
        
        if traduccion:
            print(f"[DEBUG] Traducción: {traduccion[:50]}...")
            return traduccion, "success"
        else:
            print("[WARNING] Sin traducción, usando original")
            return texto[:100], "success"
            
    except ImportError as e:
        return f"EasyOCR no disponible: {e}", "error"
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print(traceback.format_exc())
        return f"Error: {e}", "error"


def _analizar_con_ia(img_b64, api_key, prompt_vtuber, usar_google=False, modo_traduccion=False, idioma_traduccion="español"):
    # Ya no usa Groq, ahora usa PaddleOCR
    return _analizar_con_paddle(None)  # img se captura dentro


def _analizar_con_gemini(img_b64, api_key, prompt_vtuber):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": f"{prompt_vtuber}\n\nEres VTuber. Comenta lo que ves en max 2 oraciones.\n¿Qué está pasando en el juego? Comenta brevemente."},
                    {"inlineData": {"mimeType": "image/jpeg", "data": img_b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.85, "maxOutputTokens": 120}
        }
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 429:
            return None, "rate_limit"
        if r.status_code != 200:
            return f"[Error Gemini {r.status_code}]", "error"
        result = r.json()
        if "candidates" in result and len(result["candidates"]) > 0:
            parts = result["candidates"][0].get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                texto = parts[0]["text"].strip()
                for c in ["*", "#", "`", "_"]:
                    texto = texto.replace(c, "")
                return texto, "success"
        return "[Gemini: respuesta invalida]", "error"
    except Exception as e:
        return f"[Gemini error: {e}]", "error"


class GameWatcher:
    def __init__(self, api_key, speak_fn, stop_audio_fn, get_devices_fn,
                 current_prompt_fn, intervalo=30, voice="es-MX-DaliaNeural", log_fn=None,
                 modo_solo_ver=False, google_api_key=None, get_twitch_messages_fn=None,
                 leer_chat=False, leer_chat_intervalo=60):
        self.api_key        = api_key
        self.google_api_key = google_api_key
        self.speak          = speak_fn
        self.stop_audio     = stop_audio_fn
        self.get_devices    = get_devices_fn
        self.current_prompt = current_prompt_fn
        self.intervalo      = intervalo
        self.voice          = voice
        self.log            = log_fn or print
        self.modo_solo_ver  = modo_solo_ver
        self.get_twitch_messages = get_twitch_messages_fn
        self.leer_chat      = leer_chat
        self.leer_chat_intervalo = leer_chat_intervalo
        self._chat_acumulado = []
        self._ultimo_twitch_time = 0
        self.activo         = False
        self._thread        = None
        self._ultimo_hash   = ""
        self._ultimo_comentario = ""
        self._rate_limit_wait = 0
        # Modo traducción en tiempo real
        self.modo_traduccion = False
        self.idioma_traduccion = "español"

    def iniciar(self):
        if self.activo:
            self.log("⚠  Comentarista ya estaba activo")
            return
        if not PIL_OK:
            self.log("❌ Comentarista: pip install pillow")
            return
        # Ya no requiere API keys (usa PaddleOCR + traducción gratuita)
        self.activo  = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        modo = "MODO SOLO VER" if self.modo_solo_ver else "COMENTANDO"
        self.log(f"🎮 Comentarista INICIADO ({modo}) — cada {self.intervalo}s")

    def detener(self):
        self.activo = False
        self.log("⏹  Comentarista DETENIDO")

    def set_modo(self, solo_ver):
        self.modo_solo_ver = solo_ver
        modo = "MODO SOLO VER" if solo_ver else "COMENTANDO"
        self.log(f"🎮 Cambiado a {modo}")

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
            img_hash = _capturar_hash()
            img_cambio = img_hash != self._ultimo_hash

            comentario = None
            status = "no_analysis"

            if img_cambio or self.leer_chat:
                # Usar Windows Graphics Capture + PaddleOCR
                if WIN_CAPTURE_OK:
                    img = capturar_pantalla()
                else:
                    from PIL import ImageGrab
                    img = ImageGrab.grab()
                
                self.log("🔍 OCR con PaddleOCR...")
                
                comentario, status = _analizar_con_paddle(img)

                if self.leer_chat and not img_cambio:
                    self._ultimo_hash = img_hash

            if not img_cambio and not self.leer_chat:
                self.log("⏭  Sin cambios, esperando...")
                return

            if not comentario:
                self.log("⏭  Sin comentario este ciclo")
                return

            if comentario == self._ultimo_comentario:
                self.log("⏭  Comentario repetido, saltando")
                return

            self._ultimo_comentario = comentario
            self.log(f"🎮 Comentario: {comentario}")

            if self.modo_solo_ver:
                self.log("👁  Modo solo ver - sin audio")
                return

            self.stop_audio()
            _, ia_dev = self.get_devices()
            if ia_dev is not None and ia_dev != -1:
                self.speak(comentario, self.voice, ia_dev)
        except Exception as e:
            self.log(f"❌ Error comentarista: {e}")
            self.log(traceback.format_exc())
