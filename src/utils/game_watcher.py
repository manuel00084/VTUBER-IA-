"""
game_watcher.py — Comentarista de juego en tiempo real + Lector de subtítulos
3 modos: OCR Solo (RapidOCR), OCR + Vision + IA, Vision + OCR
Prioridad: Chat IA > Bot Chat > OCR > Silencio
Tecnología: RapidOCR + Karin Vision Lite + IA
"""
import threading, time, random, os, re, base64, io, gc, hashlib, json

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

import cv2
import numpy as np

WIN_CAPTURE_OK = True
from src.utils.win_capture import capturar_pantalla
from src.utils.vision import detectar_movimiento, background_subtractor_iniciar
from src.bot.twitch_bot import is_chat_ia_activo, is_bot_hablando

_ULTIMA_VEZ_IA_CHAT = 0
_ULTIMA_VEZ_BOT_CHAT = 0


def _detectar_color_dominante_simple(img):
    arr = np.array(img.resize((32, 24), Image.BILINEAR))
    r, g, b = arr[..., 0].mean(), arr[..., 1].mean(), arr[..., 2].mean()
    if r > 150 and g < 100 and b < 100: return "rojo"
    if r > 150 and g > 120 and b < 80: return "naranja"
    if r > 150 and g > 150 and b < 80: return "amarillo"
    if r < 80 and g > 120 and b < 80: return "verde"
    if r < 80 and g < 80 and b > 120: return "azul"
    if r > 120 and g < 80 and b > 120: return "morado"
    if r < 60 and g < 60 and b < 60: return "oscuro"
    if r > 180 and g > 180 and b > 180: return "claro"
    return "neutro"


class GameWatcher:
    def __init__(self, speak_fn, stop_audio_fn, get_devices_fn, log_fn=None):
        self.speak = speak_fn
        self.stop_audio = stop_audio_fn
        self.get_devices = get_devices_fn
        self.log = log_fn or print
        self._running = False
        self._thread = None
        self._ultimo_hash = ""
        self._comentarios_vistos = set()
        self.voice = "es-MX-DaliaNeural"
        self.juego_actual = "juego"
        self._modo = ""
        self._ia_key = ""
        self._ia_provider = "groq"
        self._prompt = ""
        self._game_investigated = False
        self._game_info = ""
        self._game_dimension = ""
        self._silent_desde = time.time()
        self._silent_cooldown = 20
        self._ultimo_comentario_hora = 0
        self._cooldown_comentario = 0

        # Cache para respuestas de IA
        self._ia_cache = {}
        self._ia_cache_max = 50

        # Base de datos local de juegos
        self._ruta_db = os.path.join(_PROJECT_ROOT, "data", "juegos.json")
        self._db_juegos = self._cargar_db_juegos()

        # Estado de escena para prompt adaptativo
        self._estado_escena = "tranquilo"
        self._ultimo_evento = ""
        self._eventos_recientes = []



    def _cargar_prompt(self):
        ruta_prompt = os.path.join(_PROJECT_ROOT, "prompts", "default.txt")
        try:
            cfg_path = os.path.join(_PROJECT_ROOT, "config", "config.txt")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            if k.strip() == "SELECTED_PROMPT":
                                sel = v.strip()
                                ruta = os.path.join(_PROJECT_ROOT, "prompts", sel)
                                if os.path.exists(ruta):
                                    ruta_prompt = ruta
                                break
            with open(ruta_prompt, "r", encoding="utf-8") as f:
                return f.read().strip()
        except:
            return "Eres una VTuber divertida que comenta juegos con energía."

    def _cargar_db_juegos(self):
        try:
            if os.path.exists(self._ruta_db):
                with open(self._ruta_db, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _guardar_db_juegos(self):
        try:
            with open(self._ruta_db, "w", encoding="utf-8") as f:
                json.dump(self._db_juegos, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f" Error guardando DB de juegos: {e}")

    def _info_juego_desde_db(self, nombre):
        for key in self._db_juegos:
            if key.lower() == nombre.lower():
                info = self._db_juegos[key]
                if info.get("dimension"):
                    self._game_dimension = info["dimension"]
                return info
        return None

    def _registrar_juego_en_db(self, nombre, info):
        nombre_limpio = nombre.strip()
        if not nombre_limpio:
            return
        entrada = {
            "genero": "",
            "consejo": "",
            "ideas": "",
            "dimension": "",
            "personajes": [],
            "detectar_claves": [],
            "ultima_vez": time.strftime("%Y-%m-%d")
        }
        if info and "|" in info:
            partes = info.split("|")
            if len(partes) >= 1:
                entrada["genero"] = partes[0].strip()
                if self._game_dimension:
                    entrada["dimension"] = self._game_dimension
            if len(partes) >= 2:
                entrada["consejo"] = partes[1].strip()
            if len(partes) >= 3:
                entrada["ideas"] = partes[2].strip()
        self._db_juegos[nombre_limpio] = entrada
        self._guardar_db_juegos()

    REACCIONES_PREDEFINIDAS = [
        (re.compile(r"(game\s*over|perdiste|morir|muerte|fallaste|has\s*muerto|derrota|eliminado)", re.I),
         ["¡Oh no, nos eliminaron!", "Uy, eso dolió...", "No pasa nada, a intentarlo de nuevo.",
          "¡Ánimo! La siguiente va.", "Bueno, al menos lo intentamos.", "Ay... eso no salió bien."]),
        (re.compile(r"(victoria|ganaste|completado|logro|trophy|conseguido|nivel\s*superado|exito)", re.I),
         ["¡Bien hecho!", "¡Lo sabía!", "¡Eso es maestría!", "¡Lo logramos!",
          "Increíble, qué jugada.", "Así se hace.", "¡Somos unos cracks!"]),
        (re.compile(r"(boss|jefe\s*final|enemigo|peligro|combate|lucha|pelea|guerra)", re.I),
         ["¡Cuidado!", "Algo grande se acerca...", "¡Ojo ahí!", "Esto se pone intenso.",
          "Preparados para el combate.", "Aquí viene el desastre."]),
        (re.compile(r"(pausa|opciones|ajustes|configuración|menu|inventario)", re.I),
         ["Aprovechemos para respirar.", "Mirando opciones...", "¿Qué configuramos?",
          "Tiempo de planificar.", "Veamos qué tenemos."]),
        (re.compile(r"(cargando|loading|espera|conectando)", re.I),
         ["Cargando... paciencia.", "Un momento mientras carga.", "Ya mero empezamos.",
          "Todo listo en un segundo."]),
        (re.compile(r"(vida|health|hp|energía|corazón|vidas)", re.I),
         ["Hay que cuidar la vida.", "La salud es importante.", "Revisa tu barra de vida.",
          "No te descuides.", "Tenemos que sobrevivir."]),
        (re.compile(r"(moneda|oro|dinero|plata|puntos|score|rupia|gil)", re.I),
         ["¡A juntar monedas!", "Puntos que suman.", "Hay que recolectar todo.",
          "Cada moneda cuenta.", "La economía es importante."]),
        (re.compile(r"(tesoro|cofre|item|objeto|llave|arma|armadura)", re.I),
         ["Un objeto interesante.", "¡Mira eso!", "Hay que recogerlo.",
          "Eso se ve útil.", "No lo dejes pasar."]),
        (re.compile(r"(hola|bienvenido|empezar|start|comenzar|nuevo\s*juego)", re.I),
         ["¡Empezamos!", "Aquí vamos.", "Comienza la aventura.",
          "A darle.", "Qué emoción."]),
        (re.compile(r"(jefe|nivel|stage|mundo|acto|capítulo)", re.I),
         ["Un nuevo desafío.", "Siguiente nivel.", "A ver qué nos espera.",
          "Cada vez más difícil.", "Allá vamos."]),
        (re.compile(r"(secreto|escondido|extra|bonus)", re.I),
         ["¿Un secreto?", "Hay que investigar.", "Cosas ocultas.", "Siempre hay sorpresas."]),
        (re.compile(r"(fallo|error|bug|glitch|crash)", re.I),
         ["¿Qué fue eso?", "Algo raro pasó.", "No era mi intención.", "Cosas del juego."]),
    ]

    def _reaccion_predefinida(self, texto, paddle_info=None):
        if texto:
            for patron, respuestas in self.REACCIONES_PREDEFINIDAS:
                if patron.search(texto):
                    return random.choice(respuestas)
        if paddle_info:
            objetos = paddle_info.get("objetos", [])
            nombres = [o['class_name'] for o in objetos]
            # Detectar combate: personajes + barras de vida = enemigos
            hay_vidas = any('vida' in n for n in nombres)
            hay_personajes = any('personaje' in n for n in nombres)
            hay_movimiento = any('flujo_' in n or 'shake' in n for n in nombres)
            hay_enemigos_visuales = (hay_vidas and hay_personajes) or (hay_vidas and hay_movimiento)
            if hay_enemigos_visuales and self._estado_escena != "combate":
                self._estado_escena = "combate"
                self.log(f" Estado detectado: combate por detecciones visuales")
                return "¡Parece que hay accion!"
            menus = [n for n in nombres if 'menu' in n]
            if menus:
                return "Revisando el menú."
            vidas = [n for n in nombres if 'vida' in n]
            if len(vidas) > 2 and self._estado_escena != "combate":
                self._estado_escena = "combate"
                self.log(f" Estado detectado: combate por barras de vida")
                return "¡Comienza el combate!"
        return None

    _OCR_ESTADO_MAP = [
        (re.compile(r"(boss|jefe|combate|pelea|lucha|enemigo|muerte|morir|damage|ataque|guerra)", re.I), "combate"),
        (re.compile(r"(menu|opciones|ajustes|configuraci.n|pausa|inventario|equipo)", re.I), "menu"),
        (re.compile(r"(dialogo|conversaci.n|hablar|historia|misi.n|quest|personaje)", re.I), "dialogo"),
        (re.compile(r"(explorar|buscar|mapa|tesoro|cofre|mundo|viaje)", re.I), "exploracion"),
        (re.compile(r"(cargando|loading|espera|conectando|pantalla\s*t.tulo)", re.I), "tranquilo"),
    ]

    def _detectar_estado_escena(self, paddle_info, movimiento, ocr_texto=""):
        if not paddle_info:
            return self._estado_escena
        objetos = paddle_info.get("objetos", [])
        nombres = [o['class_name'] for o in objetos]

        # Dimension: IA investigada tiene prioridad sobre deteccion visual
        dimension = None
        if self._game_dimension:
            dimension = self._game_dimension
        else:
            for n in nombres:
                if n.startswith('dimension_') or n.startswith('pixelart_') or n.startswith('smooth_'):
                    dimension = n
                    break

        hay_vidas = any('vida' in n for n in nombres)
        hay_ui = any(b in n for n in nombres for b in ('boton', 'menu'))
        hay_caras = any('cara' in n for n in nombres)
        hay_movimiento = any(f in n for n in nombres for f in ('flujo_', 'shake', 'scroll'))
        hay_personajes = any('personaje' in n for n in nombres)
        hay_actividad = movimiento.get("intensidad", 0) > 10 if movimiento else False

        # Reglas claras por prioridad
        if hay_ui and not hay_actividad:
            self._estado_escena = "menu"
        elif hay_vidas and (hay_movimiento or hay_actividad):
            self._estado_escena = "combate"
        elif hay_caras:
            self._estado_escena = "dialogo"
        elif hay_personajes and hay_movimiento:
            self._estado_escena = "exploracion"
        elif hay_actividad and hay_movimiento:
            self._estado_escena = "exploracion"
        else:
            self._estado_escena = "tranquilo"

        # OCR refuerza (prioridad sobre vision para casos claros)
        if ocr_texto:
            for patron, estado in self._OCR_ESTADO_MAP:
                if patron.search(ocr_texto):
                    self._estado_escena = estado
                    break

        return self._estado_escena

    def _adaptar_prompt_por_estado(self):
        prompts = {
            "combate": "Estamos en pleno combate. Narra con emocion, grita si pasa algo epico.",
            "menu": "Estamos en un menu o inventario. Comenta las opciones con calma y naturalidad.",
            "dialogo": "Escena de dialogo o historia. Comenta los personajes y la trama.",
            "exploracion": "Estamos explorando. Describe el entorno con curiosidad y asombro.",
            "tranquilo": "Momento tranquilo. Habla relajadamente, como si descansaras.",
        }
        return prompts.get(self._estado_escena, "Comenta lo que esta pasando naturalmente.")

    def iniciar(self, voz="es-MX-DaliaNeural", juego="juego", modo="OCR (Solo Lectura)", ia_key="", ia_provider="groq", cooldown=30):
        if self._running:
            self.log("⚠ Ya está corriendo")
            return
        self._running = True
        self.voice = voz
        self.juego_actual = juego
        self._modo = modo
        self._ia_key = ia_key
        self._ia_provider = ia_provider
        self._prompt = self._cargar_prompt()
        self._cooldown_comentario = cooldown
        self._game_investigated = False
        self._game_info = ""
        self._silent_desde = time.time()

        background_subtractor_iniciar()

        if "Groq Vision" in modo:
            self._ia_provider = "groq"
            target = self._loop_vision_ia
        elif "Google Vision" in modo:
            self._ia_provider = "google_studio"
            target = self._loop_vision_ia
        elif "Karin Animadora" in modo:
            target = self._loop_karin_animadora
        elif "Karin Vision" in modo:
            target = self._loop_ia
        elif "OCR" in modo:
            target = self._loop_solo_lectura
        else:
            target = self._loop_solo_lectura

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        self.log(f" Comentarista iniciado ({modo})")

    def detener(self):
        self._running = False
        self.log(" Comentarista detenido")

    def _puede_hablar(self):
        ahora = time.time()
        if is_chat_ia_activo():
            self.log(" Bloqueado: Chat IA activo")
            return False
        if is_bot_hablando():
            self.log(" Bloqueado: Bot hablando")
            return False
        if ahora - _ULTIMA_VEZ_IA_CHAT < 8:
            self.log(" Bloqueado: Chat IA reciente")
            return False
        if ahora - _ULTIMA_VEZ_BOT_CHAT < 3:
            self.log(" Bloqueado: Bot chat reciente")
            return False
        if ahora - self._ultimo_comentario_hora < self._cooldown_comentario:
            self.log(f" Bloqueado: Cooldown ({int(ahora - self._ultimo_comentario_hora)}s < {self._cooldown_comentario}s)")
            return False
        return True

    def _texto_valido(self, texto):
        t = texto.strip()
        if len(t) < 4:
            return False
        letras = sum(1 for c in t if c.isalpha())
        if letras < 3:
            return False
        if letras / max(len(t), 1) < 0.3:
            return False
        return True

    def _hablar(self, texto):
        if not self._puede_hablar():
            return
        if not self._texto_valido(texto):
            self.log(f" Texto invalido: {texto}")
            return
        clave = texto.strip().lower()[:100]
        if clave in self._comentarios_vistos:
            self.log(" Texto repetido, ignorado")
            return
        if len(self._comentarios_vistos) > 40:
            self._comentarios_vistos.pop()
        self._comentarios_vistos.add(clave)
        self._ultimo_comentario_hora = time.time()
        self.log(f" {texto}")
        _, ia_dev = self.get_devices()
        if ia_dev is not None and ia_dev != -1:
            self.speak(texto, self.voice, ia_dev, volume=2.0)

    def _investigar_juego(self):
        """Investiga el juego desde DB local o IA."""
        if self._game_investigated or not self._ia_key or self.juego_actual in ("juego", ""):
            return
        self._game_investigated = True

        # Buscar en DB local primero
        info_db = self._info_juego_desde_db(self.juego_actual)
        if info_db:
            partes = [info_db.get("genero",""), info_db.get("consejo",""), info_db.get("ideas","")]
            self._game_info = "|".join(partes)
            self.log(f" Info desde DB local: {info_db.get('genero','')}")
            self._hablar(f"Ahora jugamos {self.juego_actual}, un {info_db.get('genero','juego')}.")
            return

        # Si no esta en DB, preguntar a IA
        try:
            from src.ai.ia import ask_ai
            prompt_inv = (f"{self._prompt}\n\n"
                          f"El juego actual es '{self.juego_actual}'. "
                          f"Dame SOLO 4 datos separados por |: "
                          f"1) genero, 2) un consejo util, "
                          f"3) que comentar como streamer, "
                          f"4) dimension (2d, 3d, pixelart, 2.5d). "
                          f"Maximo 350 caracteres.")
            resp = ask_ai(prompt_inv, self._ia_key, self._prompt,
                          provider=self._ia_provider, max_caracteres=350)
            if resp and len(resp) > 5 and "Falta" not in resp:
                self._game_info = resp
                partes = resp.split("|")
                if len(partes) >= 4:
                    dim_raw = partes[3].strip().lower()
                    for val in ["3d", "2.5d", "pixelart", "2d"]:
                        if val in dim_raw:
                            self._game_dimension = val
                            break
                self._registrar_juego_en_db(self.juego_actual, resp)
                self.log(f" Info del juego: {resp}")
                if self._game_dimension:
                    self.log(f" Dimension detectada: {self._game_dimension}")
                self._hablar(resp)
        except Exception as e:
            self.log(f" Error investigando juego: {e}")

    def _contexto_juego_para_ia(self):
        ctx = f"Juego: {self.juego_actual}. "
        if self._game_dimension:
            ctx += f"Dimension: {self._game_dimension}. "
        if self._game_info and self.juego_actual not in ("juego", ""):
            partes = self._game_info.split('|')
            if len(partes) >= 1 and partes[0].strip():
                ctx += f"Genero: {partes[0].strip()}. "
            if len(partes) >= 2 and partes[1].strip():
                ctx += f"Consejo: {partes[1].strip()}. "
        return ctx

    def _ocr_paddle(self, img):
        """GameOCR Engine con RapidOCR optimizado para videojuegos"""
        try:
            from src.utils.game_ocr_post import post_procesar_ocr
            from src.utils.game_ocr_lite import ocr_read_text

            arr_rgb = np.array(img.convert("RGB"))
            arr_bgr = cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2BGR)

            resultados = ocr_read_text(arr_bgr, conf_min=0.3)
            resultados = post_procesar_ocr(resultados, conf_min=0.4)

            if not resultados:
                return ""

            textos = [r['text'] for r in resultados if len(r['text'].strip()) > 2]
            if textos:
                return " ".join(textos)
            return ""

        except Exception as e:
            return ""

    def _analizar_con_paddle(self, arr):
        """Analiza la escena usando Karin Vision Lite"""
        try:
            from src.vision_lite.tracking import VisionEngine

            bgr_frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if (len(arr.shape) == 3 and arr.shape[2] == 3) else arr
            engine = VisionEngine()
            dets = engine.analyze(bgr_frame, full_scan=True)

            objetos = []
            for d in dets:
                objetos.append({
                    'class_id': hash(d['class_name']) % 1000,
                    'class_name': d['class_name'],
                    'confidence': d['confidence'],
                    'box': d['box']
                })

            return {"objetos": objetos, "segmentacion": None}

        except Exception as e:
            print(f"Error en Karin Vision Lite: {e}")
            return {"objetos": [], "segmentacion": None}

    def _comentar_con_ia(self, texto, movimiento, color_dom, paddle_info=None):
        """Comentario usando IA. Solo comenta si hay juego configurado."""
        from src.ai.ia import ask_ai

        if not self.juego_actual or self.juego_actual in ("juego", ""):
            return None

        ctx = self._contexto_juego_para_ia()

        if paddle_info and paddle_info.get("objetos"):
            objs = paddle_info["objetos"]

            esc = next((o['class_name'].replace('escenario_','') for o in objs if o['class_name'].startswith('escenario_')), None)
            if esc:
                ctx += f"Estamos en un escenario de tipo {esc}. "

            vidas = [o for o in objs if o['class_name'].startswith('vida_')]
            minimapas = [o for o in objs if o['class_name'] == 'minimapa']
            patrones = [o for o in objs if o['class_name'] == 'patron_repetido']
            movs = [o for o in objs if o['class_name'] == 'movimiento']
            personas = [o for o in objs if o['class_name'] == 'persona']
            personajes = [o for o in objs if o['class_name'].startswith('personaje_')]
            botones = [o for o in objs if o['class_name'] == 'boton_ui']
            menus = [o for o in objs if o['class_name'] == 'menu_ui']
            caras = [o for o in objs if o['class_name'] == 'cara']
            brillantes = [o for o in objs if o['class_name'] == 'objeto_brillante']
            figuras = [o for o in objs if o['class_name'] == 'figura_movimiento']
            colores = [o for o in objs if 'objeto_' in o['class_name']]
            flujo_dir = [o for o in objs if o['class_name'].startswith('flujo_')]
            shake = [o for o in objs if o['class_name'] == 'shake_pantalla']
            scroll = [o for o in objs if o['class_name'] == 'scroll_pantalla']

            if personajes:
                nombres = list(set(p['class_name'].replace('personaje_','') for p in personajes))
                ctx += f"Veo personajes: {', '.join(nombres)}. "
            if personas:
                ctx += f"Hay {len(personas)} personas en pantalla. "
            if figuras or movs:
                ctx += "Hay movimiento en la escena. "
            if patrones:
                ctx += f"Veo {len(patrones)} elementos repetidos. "
            if vidas:
                ctx += "Se ven barras de vida. "
            if minimapas:
                ctx += "Hay un minimapa en pantalla. "
            if botones:
                ctx += "Veo botones en la interfaz. "
            if menus:
                ctx += "Hay un menu abierto. "
            if caras:
                ctx += "Veo rostros de personajes. "
            if brillantes:
                ctx += "Hay objetos brillantes. "
            if scroll:
                ctx += "La pantalla se esta desplazando. "
            if shake:
                ctx += "La pantalla esta temblando. "
            if flujo_dir:
                dirs = [f['class_name'].replace('flujo_','') for f in flujo_dir]
                ctx += f"La camara se mueve hacia: {', '.join(dirs)}. "
            if colores:
                colores_contados = {}
                for c in colores:
                    nom = c['class_name'].replace('objeto_','')
                    colores_contados[nom] = colores_contados.get(nom, 0) + 1
                partes = [f"{k}={v}" for k,v in sorted(colores_contados.items(), key=lambda x:-x[1])[:4]]
                ctx += f"Colores predominantes: {', '.join(partes)}. "

        # Dimension del juego (2D/3D) - IA investigada tiene prioridad
        if self._game_dimension:
            ctx += f"El juego es {self._game_dimension}. "
        else:
            dims = [o['class_name'] for o in (paddle_info.get("objetos", []) if paddle_info else []) if 'dimension_' in o['class_name'] or 'pixelart_' in o['class_name'] or 'smooth_' in o['class_name']]
            if dims:
                ctx += f"El juego se ve {dims[0].replace('_',' ')}. "

        if texto:
            texto_limpio = texto[:120].replace('"', "'")
            ctx += f'Texto en pantalla: "{texto_limpio}". '

        mov_int = movimiento.get("intensidad", 0)
        if mov_int > 5:
            ctx += f"La escena tiene {mov_int}% de actividad. "

        ctx += self._adaptar_prompt_por_estado() + " "
        ctx += "Habla como VTuber carismatica, maximo 200 caracteres, solo espanol."

        cache_key = hashlib.md5(ctx.encode()).hexdigest()
        if cache_key in self._ia_cache:
            return self._ia_cache[cache_key]

        try:
            resp = ask_ai(ctx, self._ia_key, self._prompt, provider=self._ia_provider, max_caracteres=200)
            if resp and len(resp) > 5 and "Falta" not in resp:
                self._ia_cache[cache_key] = resp
                if len(self._ia_cache) > self._ia_cache_max:
                    self._ia_cache.pop(next(iter(self._ia_cache)))
                return resp
        except:
            pass
        return None

    def _comentario_sistema(self, texto, color_dom):
        """Reglas fijas cuando no hay IA"""
        if texto:
            tl = texto.lower()
            if re.search(r"muerte|morir|game over|perdiste|fallaste", tl):
                return random.choice(["Oh no! Ánimo!", "Uy, eso dolió.", "No pasa nada, a seguir."])
            if re.search(r"victoria|ganaste|completado|logro|trophy", tl):
                return random.choice(["Bien hecho!", "Lo sabía!", "Eso es maestría."])
            if re.search(r"peligro|enemigo|boss|jefe|cuidado", tl):
                return random.choice(["Cuidado!", "Algo se acerca...", "Ojo ahí!"])
            return texto
        return None

    # ── MODOS ──────────────────────────────────────────────────────────────

    def _loop_solo_lectura(self):
        """Modo 1: OCR Solo (RapidOCR) - Optimizado para reducir CPU"""
        ultimo_tiempo_ocr = 0
        intervalo_ocr = 2.0  # Ejecutar OCR cada 2 segundos como máximo
        ultimo_hash = ""
        cambio_minimo_porcentaje = 0.1  # 10% de cambio mínimo para desencadenar OCR
        
        while self._running:
            try:
                img = capturar_pantalla()
                if img is None:
                    time.sleep(0.5)
                    continue
                
                ahora = time.time()
                
                # Saltar si aún no ha pasado el intervalo mínimo
                if ahora - ultimo_tiempo_ocr < intervalo_ocr:
                    time.sleep(0.1)
                    continue
                
                # Convertir a array numpy para comparaciones rápidas
                img_array = np.array(img)
                
                # Calcular hash ligero para detección rápida de cambios
                hash_actual = hash(img_array.tobytes()[:500])  # Menos bytes para hash más rápido
                
                # Si no hay cambio en el hash y no ha pasado mucho tiempo, esperar
                if hash_actual == ultimo_hash and (ahora - ultimo_tiempo_ocr) < (intervalo_ocr * 2):
                    time.sleep(0.1)
                    continue
                
                # Calcular cambio porcentual si tenemos frame anterior
                cambio_significativo = False
                if hasattr(self, '_ultimo_frame') and self._ultimo_frame is not None:
                    # Redimensionar para comparación más rápida (opcional)
                    small_current = cv2.resize(img_array, (160, 120))
                    small_previous = cv2.resize(self._ultimo_frame, (160, 120))
                    diff = cv2.absdiff(small_current, small_previous)
                    cambio_porcentaje = np.mean(diff) / 255.0
                    cambio_significativo = cambio_porcentaje > cambio_minimo_porcentaje
                else:
                    cambio_significativo = True  # Primer frame, siempre procesar
                
                # Ejecutar OCR si hay cambio significativo o ha pasado demasiado tiempo
                if cambio_significativo or (ahora - ultimo_tiempo_ocr) > (intervalo_ocr * 3):
                    self._ultimo_frame = img_array.copy()
                    ultimo_hash = hash_actual
                    ultimo_tiempo_ocr = ahora
                    
                    # Opcional: reducir resolución antes de OCR para acelerar
                    # img_small = img.resize((int(img.width*0.7), int(img.height*0.7)), Image.LANCZOS)
                    # texto = self._ocr_paddle(img_small)
                    texto = self._ocr_paddle(img)
                    
                    if texto:
                        prefijos = [
                            "Veo en pantalla:", "Pone:", "Dice:",
                            "El juego muestra:", " Aparece:",
                        ]
                        self._hablar(f"{random.choice(prefijos)} {texto}")
                
                time.sleep(0.2)  # Espera activa baja para respuesta razonable
                gc.collect()
            except Exception as e:
                self.log(f" Error: {e}")
                time.sleep(1)

    def _loop_ia(self):
        """Modo 2: OCR + Vision HOG + IA - Optimizado con reutilizaci�n de OCR"""
        frame_anterior = None
        ultimo_ocr = 0
        ultimo_ocr_texto = ""  # Para reutilizar resultados de OCR cuando no hay cambio significativo
        intervalo_ocr_min = 3.0  # Mínimo 3 segundos entre OCR
        intervalo_ocr_max = 8.0  # Máximo 8 segundos entre OCR forzado
        cambio_minimo_porcentaje = 0.15  # 15% de cambio mínimo para forzar nuevo OCR
        self._investigar_juego()
        while self._running:
            try:
                img = capturar_pantalla()
                if img is None:
                    time.sleep(0.5)
                    continue
                arr = np.array(img.convert("RGB"))
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                ahora = time.time()
                texto = ""
                
                # Determinar si necesitamos ejecutar OCR nuevo o podemos reutilizar
                hacer_ocr_nuevo = False
                reutilizar_ocr = False
                
                # Siempre hacer OCR si ha pasado el tiempo máximo
                if ahora - ultimo_ocr >= intervalo_ocr_max:
                    hacer_ocr_nuevo = True
                # Si ha pasado el mínimo, verificar cambio de escena
                elif ahora - ultimo_ocr >= intervalo_ocr_min:
                    movimiento = detectar_movimiento(arr, frame_anterior)
                    # Si hay movimiento significativo o es el primer frame, hacer OCR nuevo
                    if movimiento["hay"] or frame_anterior is None:
                        hacer_ocr_nuevo = True
                    # Si no hay mucho movimiento, podemos reutilizar OCR reciente
                    else:
                        # Verificar cambio de escena usando diferencia de frames
                        if hasattr(self, '_ultimo_frame_ia') and self._ultimo_frame_ia is not None:
                            # Redimensionar solo el frame actual (el anterior ya está pequeño)
                            small_current = cv2.resize(arr, (160, 120))
                            diff = cv2.absdiff(small_current, self._ultimo_frame_ia)
                            cambio_porcentaje = np.mean(diff) / 255.0
                            if cambio_porcentaje > cambio_minimo_porcentaje:
                                hacer_ocr_nuevo = True
                            else:
                                reutilizar_ocr = True  # Reutilizar OCR reciente
                        else:
                            hacer_ocr_nuevo = True  # Primer frame
                else:
                    # Antes del mínimo, intentar reutilizar si tenemos resultado reciente
                    if ultimo_ocr_texto and (ahora - ultimo_ocr) < 2:  # Reutilizar si es muy reciente
                        reutilizar_ocr = True
                
                # Detectar movimiento ANTES del paralelo (necesario para decidir)
                mov = detectar_movimiento(arr, frame_anterior)
                cambio = mov["hay"] or frame_anterior is None

                # PARALELO: ejecutar OCR y Vision al mismo tiempo
                resultado_ocr = {"texto": "", "hecho": False, "cambio": False}
                resultado_vision = {"info": {}, "hecho": False}
                hilos = []

                if hacer_ocr_nuevo:
                    def _hacer_ocr(img_p, res):
                        res["texto"] = self._ocr_paddle(img_p)
                        res["hecho"] = True
                        if res["texto"]:
                            self.log(f" OCR: {res['texto'][:80]}")
                    hilos.append(threading.Thread(target=_hacer_ocr, args=(img, resultado_ocr)))
                else:
                    if reutilizar_ocr and ultimo_ocr_texto:
                        resultado_ocr["texto"] = ultimo_ocr_texto
                    resultado_ocr["hecho"] = True

                if cambio:
                    def _hacer_vision(arr_p, res):
                        res["info"] = self._analizar_con_paddle(arr_p)
                        res["hecho"] = True
                    hilos.append(threading.Thread(target=_hacer_vision, args=(arr, resultado_vision)))
                else:
                    resultado_vision["info"] = {}
                    resultado_vision["hecho"] = True

                # Iniciar todos los hilos en paralelo
                for h in hilos:
                    h.start()

                # Esperar a que terminen
                for h in hilos:
                    h.join(timeout=15)

                texto = resultado_ocr["texto"]
                paddle_info = resultado_vision["info"]
                if hacer_ocr_nuevo:
                    ultimo_ocr = ahora
                    ultimo_ocr_texto = texto
                    self._ultimo_frame_ia = arr.copy()
                frame_anterior = arr

                # Forzar comentario si hay detecciones visuales (personas, objetos, escenario)
                hay_detecciones = bool(paddle_info and paddle_info.get("objetos"))

                if not cambio and not texto and not hay_detecciones:
                    time.sleep(0.3)
                    continue

                color_dom = _detectar_color_dominante_simple(img)

                # Detectar estado de escena para prompt adaptativo
                estado_anterior = self._estado_escena
                self._detectar_estado_escena(paddle_info, mov, ocr_texto=texto)
                if estado_anterior != self._estado_escena:
                    self.log(f" Cambio de estado: {estado_anterior} -> {self._estado_escena}")

                # Verificar reacciones predefinidas PRIMERO (sin IA)
                comentario = self._reaccion_predefinida(texto, paddle_info)
                if comentario:
                    self.log(f" Reaccion predefinida: {comentario}")
                else:
                    # Solo IA si no hay reaccion predefinida
                    comentario = self._comentar_con_ia(texto, mov, color_dom, paddle_info)
                    if comentario:
                        self.log(f" IA: {comentario}")

                if not comentario and texto:
                    comentario = self._comentario_sistema(texto, color_dom)
                if not comentario and hay_detecciones and self.juego_actual not in ("juego", ""):
                    objetos = paddle_info.get("objetos", [])
                    if objetos:
                        tipos = list(set(o['class_name'] for o in objetos[:3]))
                        comentario = f"Veo {len(objetos)} elementos en pantalla: {', '.join(tipos)}."
                        self.log(f" Fallback vision: {comentario}")
                if comentario:
                    self.log(f" Hablando: {comentario[:60]}...")
                    self._hablar(comentario)
                else:
                    self.log(" Sin comentario para generar")
                time.sleep(0.5)
                gc.collect()
            except Exception as e:
                self.log(f" Error IA: {e}")
                time.sleep(1)

    def _loop_karin_animadora(self):
        """Modo especial: OCR + Karin Animadora + IA - Entretenimiento y soporte al streamer"""
        from src.ai.ia import ask_ai
        from src.bot.twitch_bot import get_twitch_messages, is_chat_ia_activo
        import random
        import os
        
        ultimo_ocr = 0
        intervalo_ocr_min = 3.0   # Mínimo 3 segundos entre OCR
        intervalo_ocr_max = 8.0   # Máximo 8 segundos entre OCR forzado
        ultimo_chat_check = 0
        intervalo_chat = 10.0     # Revisar chat cada 10 segundos
        ultimo_saludo = 0
        intervalo_saludo = 25.0   # Enviar saludo cada 25 segundos
        
        self._investigar_juego()
        
        # Cargar frases desde archivo de base de datos
        self.frases_animadoras = []
        self.frases_recomendacion = []
        self.frases_apoyo = []
        self.frases_saludos = []
        self.frases_narradora = []
        self._pool_animadoras = []
        self._pool_recomendacion = []
        self._pool_apoyo = []
        self._pool_narradora = []
        
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            animadora_file = os.path.join(base_dir, "data", "karin_animadora.txt")
            
            if os.path.exists(animadora_file):
                with open(animadora_file, 'r', encoding='utf-8') as f:
                    contenido = f.read()
                    
                # Parsear secciones
                secciones = contenido.split('##')
                for seccion in secciones:
                    seccion = seccion.strip()
                    if seccion.startswith('Frases Motivacionales Generales'):
                        lineas = seccion.split('\n')[1:]  # Skip header
                        for linea in lineas:
                            linea = linea.strip()
                            if linea.startswith('¡') and linea.endswith('!') and len(linea) > 3:
                                self.frases_animadoras.append(linea)
                    elif seccion.startswith('Frases Motivacionales Gamer'):
                        lineas = seccion.split('\n')[1:]  # Skip header
                        for linea in lineas:
                            linea = linea.strip()
                            if linea.startswith('¡') and linea.endswith('!') and len(linea) > 3:
                                self.frases_recomendacion.append(linea)
                    elif seccion.startswith('Poesia Gamer'):
                        lineas = seccion.split('\n')[1:]  # Skip header
                        for linea in lineas:
                            linea = linea.strip()
                            if len(linea) > 10 and not linea.startswith('#'):
                                self.frases_animadoras.append(linea)  # Poesía va a animadoras
                    elif seccion.startswith('Narradora'):
                        lineas = seccion.split('\n')[1:]  # Skip header
                        for linea in lineas:
                            linea = linea.strip()
                            if len(linea) > 5 and not linea.startswith('#'):
                                self.frases_narradora.append(linea)
                    elif seccion.startswith('Saludos Personalizados'):
                        lineas = seccion.split('\n')[1:]  # Skip header
                        for linea in lineas:
                            linea = linea.strip()
                            if '[USUARIO]' in linea and len(linea) > 10:
                                self.frases_saludos.append(linea)
                                 
                # Si no se cargaron frases, usar valores por defecto
                if not self.frases_animadoras:
                    self.frases_animadoras = [
                        "¡Vamos con todo!",
                        "¡Este juego es increíble!",
                        "¡No te rindas, tú puedes!",
                        "¡Sigue así, lo estás haciendo genial!",
                        "¡Cada intento te acerca al éxito!",
                        "¡Disfruta el proceso, no solo el resultado!",
                        "¡Eres un crack jugando esto!",
                        "¡Qué buena pinta tiene este juego!",
                        "¡Sigue explorando, hay mucho por descubrir!",
                        "¡Tu estilo de juego es único!",
                        "¡No te preocupes por los errores, son parte del aprendizaje!",
                        "¡Así se juega con pasión!",
                        "¡Cada partida es una nueva aventura!",
                        "¡Confía en tus instintos de jugador!",
                        "¡Disfruta cada momento de esta experiencia!",
                    ]
                    
                if not self.frases_recomendacion:
                    self.frases_recomendacion = [
                        "¡Este juego vale totalmente la pena jugarlo!",
                        "Si te gustan los juegos de este género, este te va a encantar.",
                        "Recomendado 100% para fans de este tipo de experiencias.",
                        "Es uno de esos juegos que te atrapan desde el primer minuto.",
                        "Definitivamente vale la pena invertir tiempo en este título.",
                        "La comunidad habla muy bien de este juego, y ahora entiendo por qué.",
                        "Si buscas algo entretenido y bien hecho, este es para ti.",
                        "Los gráficos/mecánicas/historia de este juego son de primera.",
                        "Después de jugar un rato, entiendo por qué tiene tantas buenas reseñas.",
                        "Es de esos juegos que recomendaría a un amigo sin dudar.",
                    ]
                    
                if not self.frases_apoyo:
                    self.frases_apoyo = [
                        "Tranquilo/a, todos hemos estado ahí.",
                        "Los errores son oportunidades para mejorar.",
                        "No te desanimes, sigue intentándolo.",
                        "Un paso atrás para tomar dos adelante.",
                        "La práctica hace al maestro, sigue practicando.",
                        "Confía en tu proceso de aprendizaje.",
                        "Cada jugador profesional empezó exactamente donde estás ahora.",
                        "Lo importante es seguir adelante y disfrutar el camino.",
                        "Un mal momento no define tu habilidad como jugador.",
                        "Respira profundo y continúa con confianza.",
                    ]
                    
                if not self.frases_saludos:
                    self.frases_saludos = [
                        "¡Hola [USUARIO]! Gracias por pasar por el stream, tu presencia hace la diferencia.",
                        "[USUARIO], tu mensaje me hizo sonreír, sigue siendo parte de esta comunidad increíble.",
                        "¡Qué tal [USUARIO]! Tu apoyo significa el mundo para mí mientras juego.",
                        "[USUARIO], gracias por los ánimos, seguimos adelante con energía positiva.",
                        "¡Ey [USUARIO]! Tu participación en el chat hace este stream mucho más divertido.",
                        "[USUARIO], cada mensaje tuyo es como un power-up para mi moral de juego.",
                    ]
                    
                if not self.frases_narradora:
                    self.frases_narradora = [
                        "Y así, nuestro héroe avanza sin saber qué destino le espera.",
                        "En un mundo donde los píxeles cobran vida, cada decisión cuenta.",
                        "El viaje del héroe comienza con un solo paso.",
                        "No hay narrador que pueda contar mejor esta historia que tú viviéndola.",
                        "El destino del mundo digital descansa sobre tus hombros.",
                        "La pantalla parpadea, el juego te llama... ¿vas a responder?",
                    ]
            else:
                # Archivo no existe, usar valores por defecto
                self.frases_animadoras = [
                    "¡Vamos con todo!",
                    "¡Este juego es increíble!",
                    "¡No te rindas, tú puedes!",
                    "¡Sigue así, lo estás haciendo genial!",
                    "¡Cada intento te acerca al éxito!",
                    "¡Disfruta el proceso, no solo el resultado!",
                    "¡Eres un crack jugando esto!",
                    "¡Qué buena pinta tiene este juego!",
                    "¡Sigue explorando, hay mucho por descubrir!",
                    "¡Tu estilo de juego es único!",
                    "¡No te preocupes por los errores, son parte del aprendizaje!",
                    "¡Así se juega con pasión!",
                    "¡Cada partida es una nueva aventura!",
                    "¡Confía en tus instintos de jugador!",
                    "¡Disfruta cada momento de esta experiencia!",
                ]
                
                self.frases_recomendacion = [
                    "¡Este juego vale totalmente la pena jugarlo!",
                    "Si te gustan los juegos de este género, este te va a encantar.",
                    "Recomendado 100% para fans de este tipo de experiencias.",
                    "Es uno de esos juegos que te atrapan desde el primer minuto.",
                    "Definitivamente vale la pena invertir tiempo en este título.",
                    "La comunidad habla muy bien de este juego, y ahora entiendo por qué.",
                    "Si buscas algo entretenido y bien hecho, este es para ti.",
                    "Los gráficos/mecánicas/historia de este juego son de primera.",
                    "Después de jugar un rato, entiendo por qué tiene tantas buenas reseñas.",
                    "Es de esos juegos que recomendaría a un amigo sin dudar.",
                ]
                
                self.frases_apoyo = [
                    "Tranquilo/a, todos hemos estado ahí.",
                    "Los errores son oportunidades para mejorar.",
                    "No te desanimes, sigue intentándolo.",
                    "Un paso atrás para tomar dos adelante.",
                    "La práctica hace al maestro, sigue practicando.",
                    "Confía en tu proceso de aprendizaje.",
                    "Cada jugador profesional empezó exactamente donde estás ahora.",
                    "Lo importante es seguir adelante y disfrutar el camino.",
                    "Un mal momento no define tu habilidad como jugador.",
                    "Respira profundo y continúa con confianza.",
                ]
                
                self.frases_saludos = [
                    "¡Hola [USUARIO]! Gracias por pasar por el stream, tu presencia hace la diferencia.",
                    "[USUARIO], tu mensaje me hizo sonreír, sigue siendo parte de esta comunidad increíble.",
                    "¡Qué tal [USUARIO]! Tu apoyo significa el mundo para mí mientras juego.",
                    "[USUARIO], gracias por los ánimos, seguimos adelante con energía positiva.",
                    "¡Ey [USUARIO]! Tu participación en el chat hace este stream mucho más divertido.",
                    "[USUARIO], cada mensaje tuyo es como un power-up para mi moral de juego.",
                ]
        except Exception as e:
            self.log(f" Error cargando frases de Karin Animadora: {e}")
            # Valores por defecto en caso de error
            self.frases_animadoras = [
                "¡Vamos con todo!",
                "¡Este juego es increíble!",
                "¡No te rindas, tú puedes!",
                "¡Sigue así, lo estás haciendo genial!",
                "¡Cada intento te acerca al éxito!",
                "¡Disfruta el proceso, no solo el resultado!",
                "¡Eres un crack jugando esto!",
                "¡Qué buena pinta tiene este juego!",
                "¡Sigue explorando, hay mucho por descubrir!",
                "¡Tu estilo de juego es único!",
                "¡No te preocupes por los errores, son parte del aprendizaje!",
                "¡Así se juega con pasión!",
                "¡Cada partida es una nueva aventura!",
                "¡Confía en tus instintos de jugador!",
                "¡Disfruta cada momento de esta experiencia!",
            ]
            
            self.frases_recomendacion = [
                "¡Este juego vale totalmente la pena jugarlo!",
                "Si te gustan los juegos de este género, este te va a encantar.",
                "Recomendado 100% para fans de este tipo de experiencias.",
                "Es uno de esos juegos que te atrapan desde el primer minuto.",
                "Definitivamente vale la pena invertir tiempo en este título.",
                "La comunidad habla muy bien de este juego, y ahora entiendo por qué.",
                "Si buscas algo entretenido y bien hecho, este es para ti.",
                "Los gráficos/mecánicas/historia de este juego son de primera.",
                "Después de jugar un rato, entiendo por qué tiene tantas buenas reseñas.",
                "Es de esos juegos que recomendaría a un amigo sin dudar.",
            ]
            
            self.frases_apoyo = [
                "Tranquilo/a, todos hemos estado ahí.",
                "Los errores son oportunidades para mejorar.",
                "No te desanimes, sigue intentándolo.",
                "Un paso atrás para tomar dos adelante.",
                "La práctica hace al maestro, sigue practicando.",
                "Confía en tu proceso de aprendizaje.",
                "Cada jugador profesional empezó exactamente donde estás ahora.",
                "Lo importante es seguir adelante y disfrutar el camino.",
                "Un mal momento no define tu habilidad como jugador.",
                "Respira profundo y continúa con confianza.",
            ]
            
            self.frases_saludos = [
                "¡Hola [USUARIO]! Gracias por pasar por el stream, tu presencia hace la diferencia.",
                "[USUARIO], tu mensaje me hizo sonreír, sigue siendo parte de esta comunidad increíble.",
                "¡Qué tal [USUARIO]! Tu apoyo significa el mundo para mí mientras juego.",
                "[USUARIO], gracias por los ánimos, seguimos adelante con energía positiva.",
                "¡Ey [USUARIO]! Tu participación en el chat hace este stream mucho más divertido.",
                "[USUARIO], cada mensaje tuyo es como un power-up para mi moral de juego.",
            ]
            
            self.frases_narradora = [
                "Y así, nuestro héroe avanza sin saber qué destino le espera.",
                "En un mundo donde los píxeles cobran vida, cada decisión cuenta.",
                "El viaje del héroe comienza con un solo paso.",
                "No hay narrador que pueda contar mejor esta historia que tú viviéndola.",
                "El destino del mundo digital descansa sobre tus hombros.",
                "La pantalla parpadea, el juego te llama... ¿vas a responder?",
            ]
        
        # Inicializar pools de frases para evitar repeticiones
        self._pool_animadoras = self.frases_animadoras.copy()
        self._pool_recomendacion = self.frases_recomendacion.copy()
        self._pool_apoyo = self.frases_apoyo.copy()
        self._pool_narradora = self.frases_narradora.copy()
        random.shuffle(self._pool_animadoras)
        random.shuffle(self._pool_recomendacion)
        random.shuffle(self._pool_apoyo)
        random.shuffle(self._pool_narradora)
        
        # Main loop
        while self._running:
            try:
                img = capturar_pantalla()
                if img is None:
                    time.sleep(0.5)
                    continue
                    
                ahora = time.time()
                
                # Ejecutar OCR periódicamente (misma lógica que otros modos)
                hacer_ocr = False
                if ahora - ultimo_ocr >= intervalo_ocr_max:
                    hacer_ocr = True  # Tiempo máximo alcanzado
                elif ahora - ultimo_ocr >= intervalo_ocr_min:
                    # Verificar cambio significativo si ha pasado el mínimo
                    # Implementación simplificada - en modo real usaríamos detección de movimiento
                    hacer_ocr = True  # Por simplicidad en este modo, hacemos OCR frecuente
                
                texto_ocr = ""
                if hacer_ocr:
                    texto_ocr = self._ocr_paddle(img)
                    ultimo_ocr = ahora
                    
                    # Log ocasional de OCR para debug
                    if texto_ocr and len(texto_ocr) > 5:
                        self.log(f" OCR: {texto_ocr[:50]}...")
                
                # Revisar chat de Twitch periódicamente para saludos
                if ahora - ultimo_chat_check >= intervalo_chat:
                    ultimo_chat_check = ahora
                    try:
                        mensajes = get_twitch_messages(limite=10)  # Obtener últimos 10 mensajes
                        if mensajes:
                            mensaje_aleatorio = random.choice(mensajes)
                            if ":" in mensaje_aleatorio:
                                usuario_aleatorio, texto_mensaje = mensaje_aleatorio.split(":", 1)
                                usuario_aleatorio = usuario_aleatorio.strip()
                                texto_mensaje = texto_mensaje.strip()
                            else:
                                usuario_aleatorio = "Espectador"
                                texto_mensaje = mensaje_aleatorio
                            
                            # Enviar saludo usando la IA principal (no Vision)
                            prompt_saludo = (
                                f"Eres Karin, una VTuber animadora y supportive. "
                                f"El streamer está jugando '{self.juego_actual}'. "
                                f"Recibiste este mensaje del chat de Twitch: '{texto_mensaje}' "
                                f"del usuario '{usuario_aleatorio}'. "
                                f"Responde de manera positiva, animadora y cercana como haría una streamer amiga. "
                                f"Incluye el nombre del usuario en tu respuesta si es apropiado. "
                                f"Máximo 100 caracteres. Responde SIEMPRE en español."
                            )
                            
                            saludo = ask_ai(
                                text=f"Usuario {usuario_aleatorio} dice: {texto_mensaje}",
                                api_key=self._ia_key,
                                prompt=prompt_saludo,
                                provider=self._ia_provider,
                                max_caracteres=100
                            )
                            
                            if saludo and len(saludo.strip()) > 0:
                                self._hablar(saludo)
                                ultimo_saludo = ahora
                                self.log(f" Saludo al chat: {saludo}")
                                
                    except Exception as e:
                        self.log(f" Error revisando chat Twitch: {e}")
                
                # Enviar mensaje animador de forma periódica
                if ahora - ultimo_saludo >= intervalo_saludo:
                    ultimo_saludo = ahora
                    
                    # Elegir tipo de mensaje animador aleatoriamente
                    tipo_mensaje = random.choice(['animadora', 'recomendacion', 'apoyo', 'narradora'])
                    
                    # Mapeo tipo -> sección en karin_animadora.txt
                    secciones_txt = {
                        'animadora': 'Frases Motivacionales Generales',
                        'recomendacion': 'Frases Motivacionales Gamer',
                        'apoyo': 'Frases de Apoyo',
                        'narradora': 'Narradora (voz de cuentacuentos, pausada y épica)',
                    }
                    estilos_prompt = {
                        'animadora': 'animadora y motivacional, que inspire energía positiva',
                        'recomendacion': 'de recomendación sobre juegos, tipo reseña positiva',
                        'apoyo': 'de apoyo y consuelo, que anime a no rendirse',
                        'narradora': 'narrativa como de cuentacuentos, épica y pausada',
                    }
                    
                    mensaje = None
                    # Intentar generar frase nueva con IA
                    try:
                        prompt_gen = (
                            f"Eres Karin, VTuber que anima streams. "
                            f"Genera UNA SOLA frase {estilos_prompt[tipo_mensaje]} "
                            f"para alguien jugando '{self.juego_actual or 'un juego'}'. "
                            f"Máximo 120 caracteres. Sin comillas. Solo la frase. En español."
                        )
                        mensaje = ask_ai(
                            text="genera una frase",
                            api_key=self._ia_key,
                            prompt=prompt_gen,
                            provider=self._ia_provider,
                            max_caracteres=120
                        )
                        if mensaje:
                            mensaje = mensaje.strip().strip('"').strip("'")
                            if len(mensaje) > 5:
                                # Guardar en karin_animadora.txt
                                try:
                                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                                    animadora_file = os.path.join(base_dir, "data", "karin_animadora.txt")
                                    seccion = secciones_txt[tipo_mensaje]
                                    with open(animadora_file, 'r', encoding='utf-8') as f:
                                        txt = f.read()
                                    marcador = f"## {seccion}"
                                    if marcador in txt:
                                        idx = txt.index(marcador) + len(marcador)
                                        # Buscar el salto de línea después del marcador
                                        nl = txt.find('\n', idx)
                                        if nl == -1:
                                            insert_pos = len(txt)
                                        else:
                                            insert_pos = nl + 1
                                        txt = txt[:insert_pos] + '\n' + mensaje + txt[insert_pos:]
                                    else:
                                        txt = txt.rstrip('\n') + f"\n\n## {seccion}\n{mensaje}\n"
                                    with open(animadora_file, 'w', encoding='utf-8') as f:
                                        f.write(txt)
                                except Exception as e:
                                    self.log(f" Error guardando frase en txt: {e}")
                                
                                # Agregar a memoria y pool
                                if tipo_mensaje == 'animadora':
                                    self.frases_animadoras.append(mensaje)
                                    self._pool_animadoras.append(mensaje)
                                elif tipo_mensaje == 'recomendacion':
                                    self.frases_recomendacion.append(mensaje)
                                    self._pool_recomendacion.append(mensaje)
                                elif tipo_mensaje == 'narradora':
                                    self.frases_narradora.append(mensaje)
                                    self._pool_narradora.append(mensaje)
                                else:
                                    self.frases_apoyo.append(mensaje)
                                    self._pool_apoyo.append(mensaje)
                                self.log(f" Nueva frase generada ({tipo_mensaje}): {mensaje}")
                    except Exception as e:
                        self.log(f" Error generando frase con IA: {e}")
                        mensaje = None
                    
                    # Fallback si la IA falló
                    if not mensaje:
                        if tipo_mensaje == 'animadora':
                            if not self._pool_animadoras:
                                self._pool_animadoras = self.frases_animadoras.copy()
                                random.shuffle(self._pool_animadoras)
                            mensaje = self._pool_animadoras.pop()
                        elif tipo_mensaje == 'recomendacion':
                            if not self._pool_recomendacion:
                                self._pool_recomendacion = self.frases_recomendacion.copy()
                                random.shuffle(self._pool_recomendacion)
                            mensaje = self._pool_recomendacion.pop()
                        elif tipo_mensaje == 'narradora':
                            if not self._pool_narradora:
                                self._pool_narradora = self.frases_narradora.copy()
                                random.shuffle(self._pool_narradora)
                            mensaje = self._pool_narradora.pop()
                        else:
                            if not self._pool_apoyo:
                                self._pool_apoyo = self.frases_apoyo.copy()
                                random.shuffle(self._pool_apoyo)
                            mensaje = self._pool_apoyo.pop()
                    
                    # Personalizar mensaje con nombre del juego si es apropiado
                    if self.juego_actual and self.juego_actual not in ("juego", ""):
                        if tipo_mensaje == 'recomendacion':
                            mensaje = f"¡{self.juego_actual} es {mensaje.lower()}"
                        elif tipo_mensaje == 'apoyo' and random.choice([True, False]):
                            mensaje = f"En {self.juego_actual}, {mensaje.lower()}"
                        else:
                            mensaje = f"Mientras juegas {self.juego_actual}, {mensaje.lower()}"
                    
                    self._hablar(mensaje)
                    self.log(f" Mensaje animadora ({tipo_mensaje}): {mensaje}")
                
                # Tiempo de espera adaptativo
                if hacer_ocr:
                    time.sleep(3)  # Espera media después de OCR
                else:
                    time.sleep(1)  # Espera corta cuando no hay OCR
                    
            except Exception as e:
                self.log(f" Error en modo Karin Animadora: {e}")
                time.sleep(2)
    def _loop_vision_ia(self):
        """Modo Vision IA: envía captura a la IA para descripción avanzada"""
        from src.ai.ia import ask_vision
        ultimo_ocr = 0
        intervalo_ocr_min = 5.0   # Mínimo 5 segundos entre OCR
        intervalo_ocr_max = 15.0  # Máximo 15 segundos entre OCR forzado
        self._investigar_juego()
        while self._running:
            try:
                img = capturar_pantalla()
                if img is None:
                    time.sleep(2)
                    continue
                ahora = time.time()
                
                # Hash rápido para detección de cambio de escena
                img_array = np.array(img)
                hash_actual = hash(img_array.tobytes()[:300])  # Reducido para hash más rápido
                
                # Saltar si no ha cambiado mucho y no ha pasado tiempo suficiente
                tiempo_desde_ultimo_hash = ahora - getattr(self, '_ultimo_hash_tiempo', 0)
                if hash_actual == getattr(self, '_ultimo_hash', None) and tiempo_desde_ultimo_hash < 3:
                    time.sleep(0.5)
                    continue
                
                self._ultimo_hash = hash_actual
                self._ultimo_hash_tiempo = ahora
                
                # Preparar imagen para visión (siempre necesaria para Vision IA)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=60)
                b64 = base64.b64encode(buf.getvalue()).decode()
                
                # Ejecutar OCR basado en intervalos
                hacer_ocr = False
                if ahora - ultimo_ocr >= intervalo_ocr_max:
                    hacer_ocr = True  # Tiempo máximo alcanzado
                elif ahora - ultimo_ocr >= intervalo_ocr_min:
                    # Verificar cambio significativo si ha pasado el mínimo
                    # Reutilizamos el hash actual para detectar cambio
                    hash_anterior = getattr(self, '_hash_antes_ocr', None)
                    if hash_anterior is None or hash_actual != hash_anterior:
                        hacer_ocr = True
                
                texto_ocr = ""
                if hacer_ocr:
                    texto_ocr = self._ocr_paddle(img)
                    ultimo_ocr = ahora
                    self._hash_antes_ocr = hash_actual

                
                ocr_ctx = f"Texto en pantalla: '{texto_ocr[:100]}'. " if texto_ocr else ""

                # Reaccion predefinida primero (ahorra llamada Vision)
                comentario_rapido = self._reaccion_predefinida(texto_ocr)
                if comentario_rapido:
                    self.log(f" Reaccion predefinida: {comentario_rapido}")
                    self._hablar(comentario_rapido)
                    self._silent_desde = ahora
                    time.sleep(2)
                    continue

                adapt = self._adaptar_prompt_por_estado()
                tiempo_silencio = ahora - self._silent_desde
                
                # Lógica de comentario silencioso (mantenida igual pero con tiempos ajustados)
                if tiempo_silencio > self._silent_cooldown and self._puede_hablar():
                    p = (f"{self._prompt}\n\nEl juego es '{self.juego_actual}'. {ocr_ctx}"
                         f"Han pasado {int(tiempo_silencio)}s sin hablar. {adapt} "
                         f"Comenta algo espontáneo, da tu opinión o consejo. Máx 150 caracteres.")
                    resp, _, _ = ask_vision(b64, p, self._ia_key, provider=self._ia_provider)
                else:
                    p = (f"{self._prompt}\n\nEl juego es '{self.juego_actual}'. {ocr_ctx}{adapt} "
                         f"Describe la escena y da tu opinión. Máx 200 caracteres.")
                    resp, _, _ = ask_vision(b64, p, self._ia_key, provider=self._ia_provider)
                
                clave = (resp or "").strip().lower()[:80]
                if resp and clave not in self._comentarios_vistos:
                    if len(self._comentarios_vistos) > 40:
                        self._comentarios_vistos.pop()
                    self._comentarios_vistos.add(clave)
                    self._hablar(resp)
                    self._silent_desde = ahora
                
                # Tiempo de espera adaptativo basado en actividad
                if hacer_ocr or ('resp' in locals() and resp and len(resp) > 10):
                    time.sleep(2)  # Espera corta si hubo actividad
                else:
                    time.sleep(5)  # Espera más larga si todo está quieto
                    
            except Exception as e:
                self.log(f" Vision IA error: {e}")
                time.sleep(3)



