import customtkinter as ctk
import threading, os, traceback, webbrowser, requests, base64, time, json

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_VERSION = "0.9.0-beta"
APP_NAME = "Karin VTuber -IA-"

from src.core.config import load_config
from src.audio import audio_worker, speak, stop_audio, get_output_devices
from src.ai import ask_groq, ask_cerebras, ask_ai
from src.bot.twitch_bot import start_chat, get_twitch_messages
from src.core.oauth_server import TwitchOAuth, validate_token
from src.utils.ptt import PTTManager
from src.utils.game_watcher import GameWatcher
from src.utils import PIL_OK
from src.utils.translator import TranslatorManager
from PIL import Image

config = load_config()

# ===== SERVICIO DE VISIÓN CENTRALIZADO (PaddleOCR) =====
class VisionService:
    def __init__(self):
        self.running = False
        self.last_image = None
        self.last_analysis = {
            "text": "",
            "description": "",
            "game_state": "",
            "objects": [],
            "timestamp": 0
        }
        self.analysis_interval = 3.0  # segundos entre análisis
        self.last_analysis_time = 0
    
    def start(self):
        self.running = True
        threading.Thread(target=self._vision_loop, daemon=True).start()
    
    def stop(self):
        self.running = False
    
    def _vision_loop(self):
        while self.running:
            try:
                current_time = time.time()
                if current_time - self.last_analysis_time >= self.analysis_interval:
                    self._analyze_screen()
                    self.last_analysis_time = current_time
                time.sleep(0.1)
            except Exception as e:
                print(f"Vision service error: {e}")
                time.sleep(1)
    
    def _analyze_screen(self):
        """Análisis de pantalla usando PaddleOCR (gratis, offline)"""
        try:
            # Usar Windows Graphics Capture API + PaddleOCR
            from src.utils.win_capture import capturar_pantalla
            from src.utils.windows_ocr import reconocer_texto_con_posicion
            
            screenshot = capturar_pantalla()
            
            if screenshot is None:
                self.last_analysis = {"text": "Error capturando pantalla", "description": "", "game_state": "", "objects": [], "timestamp": time.time()}
                return
            
            # OCR con PaddleOCR
            bloques = reconocer_texto_con_posicion(screenshot)
            
            if bloques:
                texto = " ".join([b['original'] for b in bloques])
                self.last_analysis = {
                    "text": texto,
                    "description": f"Se detectaron {len(bloques)} elementos de texto",
                    "game_state": "",
                    "objects": [b['original'][:30] for b in bloques[:10]],  # primeros 10 textos
                    "timestamp": time.time()
                }
            else:
                self.last_analysis = {"text": "", "description": "No se detectó texto", "game_state": "", "objects": [], "timestamp": time.time()}
                
        except ImportError as e:
            self.last_analysis = {"text": f"PaddleOCR no disponible: {e}", "description": "", "game_state": "", "objects": [], "timestamp": time.time()}
        except Exception as e:
            self.last_analysis = {"text": f"Error en análisis de visión: {str(e)}", "description": "", "game_state": "", "objects": [], "timestamp": time.time()}
    
    def _analyze_with_groq(self, img_base64):
        """Analizar imagen con Groq Vision"""
        from src.core.config import load_config
        cfg = load_config()
        api_key = cfg.get("GROQ_API_KEY", "")
        
        # Prompt para análisis múltiple
        prompt = """Analiza esta imagen y proporciona:
1. Texto extraído (OCR) - todo el texto visible
2. Descripción general de lo que se ve
3. Estado del juego si es un juego (elementos interactivos, puntuación, etc.)
4. Lista de objetos/interfaces detectados

Responde en formato JSON:
{
  "text": "texto extraído aquí",
  "description": "descripción general",
  "game_state": "estado del juego o empty si no es juego",
  "objects": ["objeto1", "objeto2", ...]
}"""
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.2-11b-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Intentar parsear como JSON
            try:
                import json
                analysis = json.loads(content)
                self.last_analysis = {
                    "text": analysis.get("text", ""),
                    "description": analysis.get("description", ""),
                    "game_state": analysis.get("game_state", ""),
                    "objects": analysis.get("objects", []),
                    "timestamp": time.time()
                }
            except:
                # Si no es JSON, guardar como texto
                self.last_analysis = {
                    "text": content,
                    "description": content[:200] + "..." if len(content) > 200 else content,
                    "game_state": "",
                    "objects": [],
                    "timestamp": time.time()
                }
        else:
            raise Exception(f"Groq API error: {response.status_code}")
    
    def _analyze_with_google(self, img_base64):
        """Analizar imagen con Google Gemini Vision"""
        from src.core.config import load_config
        cfg = load_config()
        api_key = cfg.get("GOOGLE_AI_API_KEY", "")
        
        # Prompt para análisis múltiple
        prompt = """Analyze this image and provide:
1. Extracted text (OCR) - all visible text
2. General description of what you see
3. Game state if it's a game (interactive elements, score, etc.)
4. List of detected objects/interfaces

Respond in JSON format:
{
  "text": "extracted text here",
  "description": "general description",
  "game_state": "game state or empty if not a game",
  "objects": ["object1", "object2", ...]
}"""
        
        # Google Gemini API endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": img_base64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 1024,
            }
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            # Extract text from Gemini response
            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if len(parts) > 0 and "text" in parts[0]:
                        content = parts[0]["text"]
                        
                        # Intentar parsear como JSON
                        try:
                            import json
                            analysis = json.loads(content)
                            self.last_analysis = {
                                "text": analysis.get("text", ""),
                                "description": analysis.get("description", ""),
                                "game_state": analysis.get("game_state", ""),
                                "objects": analysis.get("objects", []),
                                "timestamp": time.time()
                            }
                        except:
                            # Si no es JSON, guardar como texto
                            self.last_analysis = {
                                "text": content,
                                "description": content[:200] + "..." if len(content) > 200 else content,
                                "game_state": "",
                                "objects": [],
                                "timestamp": time.time()
                            }
                    else:
                        raise Exception("No text content in Gemini response")
                else:
                    raise Exception("Invalid Gemini response structure")
            else:
                raise Exception("No candidates in Gemini response")
        else:
            raise Exception(f"Google Gemini API error: {response.status_code}")
    
    def get_analysis(self):
        return self.last_analysis.copy()
    
    def get_text_only(self):
        return self.last_analysis.get("text", "")
    
    def get_description(self):
        return self.last_analysis.get("description", "")
    
    def get_game_state(self):
        return self.last_analysis.get("game_state", "")

vision_service = VisionService()

# Paleta based on avatar.png - Pink/Purple theme
BG     = "#1a0a1e"; SIDE   = "#150a20"; CARD  = "#2a1040"; CARD2 = "#3a1550"
BORD   = "#ff69b4"; PURP   = "#ff69b4"
GRN    = "#166534"; GRN_T  = "#bbf7d0"
RED    = "#7f1d1d"; RED_T  = "#fca5a5"
BLU    = "#1e3a5f"; BLU_T  = "#93c5fd"
AMB    = "#78350f"; AMB_T  = "#fcd34d"

TXT    = "#fce7f3"; MUT    = "#f9a8d4"; LOGBG = "#0f0518"

def mk(p, **k):
    k.setdefault("fg_color", CARD); k.setdefault("corner_radius", 10)
    return ctk.CTkFrame(p, **k)

def lb(p, t, sz=12, col=TXT, bold=False, **k):
    return ctk.CTkLabel(p, text=t, font=("Arial", sz, "bold" if bold else "normal"),
                        text_color=col, **k)

def cb(p, vals, **k):
    k.setdefault("fg_color", CARD); k.setdefault("border_color", BORD)
    k.setdefault("button_color", BORD); k.setdefault("dropdown_fg_color", CARD)
    k.setdefault("font", ("Arial", 11))
    return ctk.CTkComboBox(p, values=vals, **k)

def bt(p, t, bg, fg, cmd, h=36, **k):
    return ctk.CTkButton(p, text=t, fg_color=bg, text_color=fg, hover_color=bg,
                         font=("Arial", 12, "bold"), corner_radius=8, height=h,
                         command=cmd, **k)


# ════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        print("App.__init__ started")
        super().__init__()
        print("super().__init__ done")
        self.title(f"{APP_NAME} v{APP_VERSION}")
        print("title set")
        self.geometry("920x650")
        print("geometry set")
        
        # Nota: El icono de ventana requiere formato .ico, pero la app funciona sin él
        self.minsize(880, 580)
        print("minsize set")
        self.configure(fg_color=BG)
        print("configure done")

        print("Starting audio worker thread...")
        threading.Thread(target=audio_worker, daemon=True).start()
        print("Audio worker thread started")
        print("Audio worker thread started")

        # Prompts
        self.prompt_folder = os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        os.makedirs(self.prompt_folder, exist_ok=True)
        self.prompt_files = [f for f in os.listdir(self.prompt_folder) if f.endswith(".txt")]
        if not self.prompt_files:
            p = os.path.join(self.prompt_folder, "default.txt")
            open(p, "w", encoding="utf-8").write("Eres una VTuber divertida.")
            self.prompt_files = ["default.txt"]
        
        # Cargar la personalidad guardada o usar la primera por defecto
        selected_prompt_file = config.get("SELECTED_PROMPT", self.prompt_files[0])
        # Verificar que el archivo guardado existe, si no usar el primero
        if selected_prompt_file not in self.prompt_files:
            selected_prompt_file = self.prompt_files[0]
        
        with open(os.path.join(self.prompt_folder, selected_prompt_file), encoding="utf-8") as f:
            self.current_prompt = f.read()
        self._selected_prompt_file = selected_prompt_file

        self.devices   = get_output_devices()
        self.dev_names = [n for n, _ in self.devices] or ["Default"]

        # Restaurar dispositivos seleccionados desde config
        sp_idx = int(config.get("SPEAKER_DEVICE", 0))
        ia_idx = int(config.get("IA_DEVICE", 0))
        if sp_idx < len(self.dev_names):
            self._sp_default = self.dev_names[sp_idx]
        else:
            self._sp_default = self.dev_names[0] if self.dev_names else "Default"
        if ia_idx < len(self.dev_names):
            self._ia_default = self.dev_names[ia_idx]
        else:
            self._ia_default = self.dev_names[0] if self.dev_names else "Default"
        
        # Restaurar configuración Bot Chat IA
        self._ia_command = config.get("BOT_IA_COMMAND", "!IA")
        self._ia_voice = config.get("BOT_IA_VOICE", "es-MX-DaliaNeural")
        self.game_watcher = None
        self.translator = None
        
        # Iniciar servicio de visión
        vision_service.start()
        
        # Todas las voces disponibles
        self.voices_all = ["es_ES-ElviraNeural", "es_ES-AlvaroNeural",
                           "es_MX-DaliaNeural", "es_MX-LiaNeural", "es_MX-DarioNeural",
                           "es_AR-EmiliaNeural", "es_AR-TonoNeural"]

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()

        # PTT
        saved_ptt_key = config.get("PTT_KEY", "F9")
        if PTTManager:
            try:
                self.ptt_obj = PTTManager(
                    app=self, ask_ai_fn=ask_ai, speak=speak,
                    stop_audio=stop_audio, config=config,
                    get_devices=self.get_devices,
                    current_prompt=lambda: self.current_prompt,
                    key=saved_ptt_key.lower(), voice="es-MX-DaliaNeural")
                self.log(f"⌨  PTT listo — mantén CTRL+{saved_ptt_key} para hablar")
            except Exception as e:
                self.log(f"⚠  PTT error: {e}")
        else:
            self.log("⚠  PTT no disponible — pip install keyboard")

        if not PIL_OK:
            self.log("Comentarista: pip install pillow")
    
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=SIDE, corner_radius=0, width=200)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(8, weight=1)

        hdr = ctk.CTkFrame(sb, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(16, 4))
        
        # Agregar logo
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "logo", "avatar.png")
            logo_img = ctk.CTkImage(light_image=Image.open(logo_path), size=(80, 80))
            ctk.CTkLabel(hdr, image=logo_img, text="").pack(anchor="center", pady=(0, 8))
        except Exception as e:
            print(f"Error cargando logo: {e}")
        
        lb(hdr, "Karin VTuber -IA-", sz=16, bold=True, col="#ff69b4").pack(anchor="center")

        ctk.CTkFrame(sb, height=1, fg_color=BORD).grid(row=1, column=0, sticky="ew", padx=8)

        self._nav_btns = {}
        buttons = [
            ("Panel",        "panel"),
            ("Audio",        "audio"),
            ("Traductor",    "traductor"),
            ("Bot Speaker",  "bot_speaker"),
            ("API_KEY",      "api_key"),
            ("Creditos",     "creditos"),
        ]
        
        for i, (txt, key) in enumerate(buttons):
            b = ctk.CTkButton(sb, text=txt, anchor="w", fg_color="transparent",
                              text_color=MUT, hover_color=CARD2, font=("Arial", 12),
                              corner_radius=8, height=34,
                              command=lambda k=key: self._tab(k))
            b.grid(row=3+i, column=0, sticky="ew", padx=6, pady=1)
            self._nav_btns[key] = b

        ctk.CTkFrame(sb, height=1, fg_color=BORD).grid(row=9, column=0, sticky="ew", padx=8, pady=6)

        # Botón conectar Twitch (visible)
        self.twitch_btn = ctk.CTkButton(
            sb, text="Conectar Twitch", fg_color=PURP, text_color="#fff",
            hover_color="#7c58c0", font=("Arial", 11, "bold"), corner_radius=8,
            height=30, command=self.connect_twitch)
        self.twitch_btn.grid(row=10, column=0, padx=8, pady=(4, 4), sticky="ew")

    def _tab(self, key):
        for k, b in self._nav_btns.items():
            b.configure(fg_color=CARD2 if k == key else "transparent",
                        text_color=TXT if k == key else MUT)
        for k, f in self._tabs.items():
            if k == key:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_remove()

    # ════════════════════════════════════════════════════════════════════════
    #  CONTENIDO
    # ════════════════════════════════════════════════════════════════════════
    def _build_content(self):
        wrap = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        wrap.grid(row=0, column=1, sticky="nsew")
        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        # Topbar
        top = ctk.CTkFrame(wrap, fg_color=SIDE, corner_radius=0, height=46)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)
        lb(top, "Panel de control", sz=13, bold=True).grid(row=0, column=0, padx=14, pady=12, sticky="w")
        tf = ctk.CTkFrame(top, fg_color="transparent")
        tf.grid(row=0, column=2, padx=8, sticky="e")
        bt(tf, "⏹ Audio", RED,  RED_T,  stop_audio,    h=28, width=90).pack(side="left", padx=2)
        bt(tf, "🧪 Voz",  BLU,  BLU_T,  self.test_voice, h=28, width=80).pack(side="left", padx=2)
        bt(tf, "🤖 IA",   CARD2, TXT,   self.test_ia,    h=28, width=72).pack(side="left", padx=(2, 8))

        # Área tabs
        area = ctk.CTkFrame(wrap, fg_color=BG, corner_radius=0)
        area.grid(row=0, column=0, sticky="nsew")
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)
        
        # Definir todas las voces para usar en el panel
        self.voices_all = ["es_ES-ElviraNeural", "es_ES-AlvaroNeural",
                           "es_MX-DaliaNeural", "es_MX-LiaNeural", "es_MX-DarioNeural",
                           "es_AR-EmiliaNeural", "es_AR-TonoNeural"]

        self._tabs = {
            "panel":        self._tab_panel(area),
            "audio":        self._tab_audio(area),
            "traductor":    self._tab_traductor(area),
            "bot_speaker":  self._tab_bot_speaker(area),
            "api_key":      self._tab_api_key(area),
            "creditos":     self._tab_creditos(area),
        }
        self._tab("panel")
        self._nav_btns["panel"].configure(fg_color=CARD2, text_color=TXT)

    # ════════════════════════════════════════════════════════════════════════
    #  TAB PANEL
    # ════════════════════════════════════════════════════════════════════════
    def _tab_panel(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        # Log
        lc = mk(tab)
        lc.pack(fill="x", padx=14, pady=(12, 6))
        lb(lc, "📋  Actividad", sz=11, bold=True).pack(anchor="w", padx=10, pady=(8, 2))
        self.log_box = ctk.CTkTextbox(lc, height=120, font=("Consolas", 11),
                                      fg_color=LOGBG, text_color="#7dd3fc",
                                      border_width=0, corner_radius=6)
        self.log_box.pack(fill="x", padx=10, pady=(0, 10))

        # Grid 2 columnas
        g = ctk.CTkFrame(tab, fg_color="transparent")
        g.pack(fill="both", expand=True, padx=14, pady=4)
        g.grid_columnconfigure((0, 1), weight=1)
        g.grid_rowconfigure((0, 1), weight=1)

        # Personalidad
        cp = mk(g, fg_color=CARD2)
        cp.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))
        lb(cp, "Personalidad", sz=11, bold=True, col=MUT).pack(anchor="w", padx=10, pady=(8, 2))
        lb(cp, "Prompt", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        self.mode_select = cb(cp, self.prompt_files, command=self.change_mode)
        self.mode_select.pack(fill="x", padx=10, pady=(0, 3)); 
        # Establecer la personalidad guardada o la primera por defecto
        initial_prompt = config.get("SELECTED_PROMPT", self.prompt_files[0])
        if initial_prompt not in self.prompt_files:
            initial_prompt = self.prompt_files[0]
        self.mode_select.set(initial_prompt)
        
        # Botón para crear nuevo prompt
        btn_new_prompt = ctk.CTkButton(cp, text="+ Nueva Personalidad", fg_color=CARD, text_color=TXT,
                                       hover_color=BORD, height=28, corner_radius=6,
                                       command=self._crear_nuevo_prompt)
        btn_new_prompt.pack(fill="x", padx=10, pady=(4, 4))

        # Botones de memoria y guardar
        bp = ctk.CTkFrame(cp, fg_color="transparent")
        bp.pack(fill="x", padx=10, pady=(6, 4))
        bp.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(bp, text="🗑  Borrar memoria", fg_color=RED, text_color=RED_T,
                      hover_color="#991b1b", height=32, corner_radius=6,
                      command=self._borrar_memoria).grid(row=0, column=0, padx=(0, 3), sticky="ew")
        ctk.CTkButton(bp, text="💾 Guardar config", fg_color=GRN, text_color=GRN_T,
                      hover_color="#22c55e", height=32, corner_radius=6,
                      command=self._guardar_config_panel).grid(row=0, column=1, padx=(3, 0), sticky="ew")
        ctk.CTkFrame(cp, height=6, fg_color="transparent").pack()

        # PTT rápido
        cv = mk(g, fg_color=CARD2)
        cv.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=(0, 5))
        lb(cv, "🎤  PTT", sz=11, bold=True, col=MUT).pack(anchor="w", padx=10, pady=(8, 4))
        inf = mk(cv, fg_color=CARD)
        inf.pack(fill="x", padx=10, pady=(0, 4))
        ir = ctk.CTkFrame(inf, fg_color="transparent")
        ir.pack(fill="x", padx=8, pady=6)
        lb(ir, "CTRL +", sz=11, col=TXT).pack(side="left", padx=(0, 4))
        self.ptt_key_entry = ctk.CTkEntry(ir, width=60, font=("Consolas", 12, "bold"),
                                           fg_color=BG, text_color=TXT, border_color=BORD,
                                           justify="center")
        self.ptt_key_entry.pack(side="left", padx=(0, 8))
        saved_ptt_key = config.get("PTT_KEY", "F9")
        self.ptt_key_entry.insert(0, saved_ptt_key)
        lb(ir, "Mantén para hablar", sz=10, col=MUT).pack(side="left")
        br = ctk.CTkFrame(cv, fg_color="transparent")
        br.pack(fill="x", padx=10, pady=(0, 8))
        br.grid_columnconfigure((0, 1), weight=1)
        bt(br, "🎤 Hablar", GRN,  GRN_T,    self.ptt_click, h=32).grid(row=0, column=0, padx=(0, 3), sticky="ew")
        bt(br, "🤖 Test",  PURP, "#e9d5ff", self.test_ia,   h=32).grid(row=0, column=1, padx=(3, 0), sticky="ew")

        # Bot Chat IA
        ia_frame = mk(tab, fg_color=CARD2)
        ia_frame.pack(fill="x", padx=14, pady=(10, 6))
        lb(ia_frame, "💬  Bot Chat IA", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        
        # Comando IA
        cmd_ia_frame = mk(ia_frame, fg_color="transparent")
        cmd_ia_frame.pack(fill="x", padx=10, pady=(0, 8))
        lb(cmd_ia_frame, "📝  Comando para activar IA:", sz=11, bold=True).pack(anchor="w", padx=10, pady=(10, 4))
        self.ia_command_entry = ctk.CTkEntry(cmd_ia_frame, placeholder_text="!IA",
                                           font=("Consolas", 12),
                                           fg_color=CARD, text_color=TXT, border_color=BORD)
        self.ia_command_entry.pack(fill="x", padx=10, pady=(0, 4))
        self.ia_command_entry.insert(0, config.get("BOT_IA_COMMAND", "!IA"))
        
# Voz IA
        lb(ia_frame, "Voz para respuestas IA:", sz=11, bold=True).pack(anchor="w", padx=10, pady=(10, 4))
        saved_ia_voice = config.get("BOT_IA_VOICE", "es-MX-DaliaNeural")
        self.ia_voice_var = ctk.StringVar(value=saved_ia_voice)
        
        self.ia_voice_menu = ctk.CTkOptionMenu(ia_frame, values=self.voices_all,
                                             variable=self.ia_voice_var,
                                             fg_color=CARD, button_color=BORD, dropdown_fg_color=CARD2,
                                             text_color=TXT, font=("Arial", 11))
        self.ia_voice_menu.pack(fill="x", padx=10, pady=(0, 6))
        
        # Botón guardar
        btn_ia = ctk.CTkButton(ia_frame, text="💾 Guardar Config IA", fg_color=GRN, text_color=GRN_T,
                              height=28, corner_radius=6, hover_color="#22c55e",
                              command=self._guardar_ia_config)
        btn_ia.pack(padx=10, pady=(0, 10))
        
        # Botón test voz IA
        btn_test_ia = ctk.CTkButton(ia_frame, text="🧪 Test Voz IA", fg_color=PURP, text_color="#e9d5ff",
                                   height=28, corner_radius=6,
                                   command=self._test_ia_voice)
        btn_test_ia.pack(padx=10, pady=(0, 10))
        
        # ── Comentarista ──────────────────────────────────────────────
        cmt_frame = mk(ia_frame, fg_color=CARD)
        cmt_frame.pack(fill="x", padx=10, pady=(0, 8))
        lb(cmt_frame, "🎮  Comentarista de juego", sz=11, bold=True).pack(anchor="w", padx=10, pady=(8, 4))
        
        self.comentarista_activo = ctk.BooleanVar(value=False)
        cmt_switch = ctk.CTkSwitch(cmt_frame, text="Activar comentarista",
                                    variable=self.comentarista_activo,
                                    fg_color=CARD2, button_color=PURP,
                                    progress_color=BORD, font=("Arial", 11),
                                    command=self.toggle_watcher)
        cmt_switch.pack(anchor="w", padx=10, pady=(0, 4))
        
        saved_leer_chat = config.get("COMENTARISTA_LEER_CHAT", False)
        self.comentarista_leer_chat = ctk.BooleanVar(value=saved_leer_chat)
        ctk.CTkSwitch(cmt_frame, text="   Leer chat de Twitch",
                      variable=self.comentarista_leer_chat,
                      fg_color=CARD2, button_color=BLU,
                      progress_color=BORD, font=("Arial", 10)).pack(anchor="w", padx=10, pady=(0, 8))
        
        return tab

    # ════════════════════════════════════════════════════════════════════════
    #  TAB AUDIO
    # ════════════════════════════════════════════════════════════════════════
    def _tab_audio(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🔊  Dispositivos de audio", sz=12, bold=True).pack(anchor="w", padx=10, pady=(10, 4))
        for txt, attr, default in [
            ("Bot Speaker", "sp2", self._sp_default),
            ("IA Voz", "ia2", self._ia_default),
            ("Monitor", "mn2", self._sp_default),
        ]:
            lb(c, txt, sz=10, col=MUT).pack(anchor="w", padx=10, pady=(4, 0))
            vals = (["(Ninguno)"] + self.dev_names) if "Monitor" in txt else self.dev_names
            bx = cb(c, vals); bx.pack(fill="x", padx=10, pady=(0, 4))
            if default in vals:
                bx.set(default)
            else:
                bx.set(vals[0])
            setattr(self, attr, bx)
        ctk.CTkFrame(c, height=6, fg_color="transparent").pack()
        
        # Equalizador
        eq_frame = mk(tab, fg_color=CARD2)
        eq_frame.pack(fill="x", padx=14, pady=(12, 6))
        lb(eq_frame, "🎛  Equalizador de voz IA", sz=12, bold=True).pack(anchor="w", padx=10, pady=(10, 4))
        
        # Graves (Bass)
        bass_frame = ctk.CTkFrame(eq_frame, fg_color="transparent")
        bass_frame.pack(fill="x", padx=10, pady=(4, 4))
        lb(bass_frame, "🎸 Graves (Bass):", sz=10, col=MUT).pack(side="left")
        self.bass_var = ctk.IntVar(value=config.get("EQ_BASS", 0))
        bass_slider = ctk.CTkSlider(bass_frame, from_=-12, to=12, number_of_steps=24,
                                  variable=self.bass_var, fg_color=CARD, progress_color=BORD)
        bass_slider.pack(side="left", fill="x", expand=True, padx=(8, 8))
        lb(bass_frame, "0", sz=9, col=MUT, width=30).pack(side="right")
        
        # Agudos (Treble)
        treble_frame = ctk.CTkFrame(eq_frame, fg_color="transparent")
        treble_frame.pack(fill="x", padx=10, pady=(0, 4))
        lb(treble_frame, "🎵 Agudos (Treble):", sz=10, col=MUT).pack(side="left")
        self.treble_var = ctk.IntVar(value=config.get("EQ_TREBLE", 0))
        treble_slider = ctk.CTkSlider(treble_frame, from_=-12, to=12, number_of_steps=24,
                                  variable=self.treble_var, fg_color=CARD, progress_color=BORD)
        treble_slider.pack(side="left", fill="x", expand=True, padx=(8, 8))
        lb(treble_frame, "0", sz=9, col=MUT, width=30).pack(side="right")
        
        # Velocidad (Speed)
        speed_frame = ctk.CTkFrame(eq_frame, fg_color="transparent")
        speed_frame.pack(fill="x", padx=10, pady=(0, 4))
        lb(speed_frame, "⚡ Velocidad:", sz=10, col=MUT).pack(side="left")
        self.speed_var = ctk.IntVar(value=config.get("EQ_SPEED", 0))
        speed_slider = ctk.CTkSlider(speed_frame, from_=-50, to=50, number_of_steps=100,
                                    variable=self.speed_var, fg_color=CARD, progress_color=BORD)
        speed_slider.pack(side="left", fill="x", expand=True, padx=(8, 8))
        lb(speed_frame, "0%", sz=9, col=MUT, width=30).pack(side="right")
        
        # Auto-Tune
        autotune_frame = ctk.CTkFrame(eq_frame, fg_color="transparent")
        autotune_frame.pack(fill="x", padx=10, pady=(0, 4))
        lb(autotune_frame, "🎤 Auto-Tune:", sz=10, col=MUT).pack(side="left")
        self.autotune_var = ctk.IntVar(value=config.get("EQ_AUTOTUNE", 0))
        autotune_slider = ctk.CTkSlider(autotune_frame, from_=0, to=100, number_of_steps=100,
                                    variable=self.autotune_var, fg_color=CARD, progress_color=BORD)
        autotune_slider.pack(side="left", fill="x", expand=True, padx=(8, 8))
        lb(autotune_frame, "0%", sz=9, col=MUT, width=30).pack(side="right")
        
        # Botón guardar ecualizador
        eq_btn = ctk.CTkButton(eq_frame, text="💾 Guardar EQ", fg_color=GRN, text_color=GRN_T,
                              height=26, corner_radius=6, hover_color="#22c55e",
                              command=self._guardar_eq)
        eq_btn.pack(padx=10, pady=(8, 10))
        
        return tab

    # ════════════════════════════════════════════════════════════════════════
    #  TAB TRADUCTOR
    # ════════════════════════════════════════════════════════════════════════
    def _tab_traductor(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🈳  Traductor en tiempo real", sz=12, bold=True).pack(anchor="w", padx=10, pady=(10, 6))

# Traducir a + Motor de traducción
        opt_row = ctk.CTkFrame(c, fg_color="transparent")
        opt_row.pack(fill="x", padx=10, pady=(0, 6))
        lb(opt_row, "OCR: EasyOCR (offline)", sz=11, col=MUT).pack(side="left", padx=(0, 6))
        lb(opt_row, "Traducir a:", sz=11, col=MUT).pack(side="left", padx=(0, 6))
        self.idioma_var = ctk.StringVar(value="español")
        cb(opt_row, ["español", "inglés", "portugués", "francés", "alemán"],
           variable=self.idioma_var).pack(side="left", padx=(0, 12))
        
        # Voz para traducción
        self.leer_voz_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(opt_row, text="🔊 Voz", variable=self.leer_voz_var,
                      fg_color=CARD2, button_color=GRN,
                      progress_color=BORD, font=("Arial", 10)).pack(side="left", padx=(12, 0))
        
        # Motor de traducción (todos gratuitos)
        lb(opt_row, "Motor:", sz=11, col=MUT).pack(side="left", padx=(12, 6))
        self.trad_motor = ctk.CTkOptionMenu(opt_row, values=["Google (gratis)", "MyMemory (gratis)"],
                                             fg_color=CARD, button_color=BORD, dropdown_fg_color=CARD2,
                                             text_color=TXT, font=("Arial", 11))
        self.trad_motor.pack(side="left", fill="x", expand=True)
        
        g = ctk.CTkFrame(c, fg_color="transparent")
        g.pack(fill="x", padx=10, pady=(0, 6))
        g.grid_columnconfigure((0, 1), weight=1)
        for txt, ico, bgc, fgc, cmd, r, col in [
            ("Capturar área",     "📷", BLU,   BLU_T,  self.trad_area_unica,    0, 0),
            ("Pantalla completa", "🖥", CARD2, TXT,    self.trad_pantalla_unica, 0, 1),
            ("Área continua",     "🔄", AMB,   AMB_T,  self.trad_continuo_area,  1, 0),
            ("Pantalla continua", "♾", AMB,   AMB_T,  self.trad_continuo_full,  1, 1),
        ]:
            ctk.CTkButton(g, text=f"{ico}  {txt}", fg_color=bgc, text_color=fgc,
                          hover_color=bgc, font=("Arial", 12, "bold"),
                          corner_radius=8, height=42, command=cmd).grid(
                              row=r, column=col, padx=4, pady=4, sticky="ew")
        si = ctk.CTkFrame(c, fg_color="transparent")
        si.pack(fill="x", padx=10, pady=(0, 4))
        lb(si, "Intervalo:", sz=11, col=MUT).pack(side="left")
        self.trad_intervalo_var = ctk.IntVar(value=4)
        self._tlbl = lb(si, "4s", sz=11, bold=True)
        ctk.CTkSlider(si, from_=2, to=30, number_of_steps=28,
                      variable=self.trad_intervalo_var, fg_color=BORD,
                      progress_color=PURP, button_color=PURP, button_hover_color="#7c58c0",
                      command=lambda v: self._tlbl.configure(text=f"{int(v)}s")).pack(
                          side="left", fill="x", expand=True, padx=8)
        self._tlbl.pack(side="left", padx=(0, 4))
        self.btn_detener_trad = bt(c, "⏹  Detener traducción", RED, RED_T,
                                   self.detener_traduccion, h=34)
        self.btn_detener_trad.pack(fill="x", padx=10, pady=(2, 10))
        self.btn_detener_trad.configure(state="disabled")
        return tab

    # ════════════════════════════════════════════════════════════════════════
    #  TAB BOT SPEAKER
    # ════════════════════════════════════════════════════════════════════════
    def _tab_bot_speaker(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🔧  Bot Speaker", sz=12, bold=True).pack(anchor="w", padx=10, pady=(10, 2))
        lb(c, "Comandos para reproducir audio en Twitch.", sz=10, col=MUT).pack(
            anchor="w", padx=10, pady=(0, 8))

        self.voices_male = ["es_ES-AlvaroNeural", "es_MX-DarioNeural", "es_AR-TonoNeural"]
        self.voices_female = ["es_ES-ElviraNeural", "es_MX-LiaNeural", "es_MX-DaliaNeural", "es_AR-EmiliaNeural"]

        cmd_frame = mk(c, fg_color=CARD2)
        cmd_frame.pack(fill="x", padx=10, pady=(0, 8))
        lb(cmd_frame, "📝  ComandoSpeak (voz masculina):", sz=11, bold=True).pack(anchor="w", padx=10, pady=(10, 4))
        self.cmd_speak_entry = ctk.CTkEntry(cmd_frame, placeholder_text="!sp",
                                        font=("Consolas", 12),
                                        fg_color=CARD, text_color=TXT, border_color=BORD)
        self.cmd_speak_entry.pack(fill="x", padx=10, pady=(0, 4))
        self.cmd_speak_entry.insert(0, config.get("BOT_SPEAK_CMD", "!sp"))

        self.voice_male_var = ctk.StringVar(value=config.get("BOT_VOICE_MALE", "es_MX-DarioNeural"))
        self.voice_male_menu = ctk.CTkOptionMenu(cmd_frame, values=self.voices_male,
                                              variable=self.voice_male_var,
                                              fg_color=CARD, button_color=BORD, dropdown_fg_color=CARD2,
                                              text_color=TXT, font=("Arial", 11))
        self.voice_male_menu.pack(fill="x", padx=10, pady=(0, 6))

        lb(cmd_frame, "ComandoSpeakMap (voz femenina):", sz=11, bold=True).pack(anchor="w", padx=10, pady=(10, 4))
        self.cmd_speakmap_entry = ctk.CTkEntry(cmd_frame, placeholder_text="!spm",
                                              font=("Consolas", 12),
                                              fg_color=CARD, text_color=TXT, border_color=BORD)
        self.cmd_speakmap_entry.pack(fill="x", padx=10, pady=(0, 4))
        self.cmd_speakmap_entry.insert(0, config.get("BOT_SPEAKMAP_CMD", "!spm"))

        saved_male = config.get("BOT_VOICE_MALE", "es_MX-DarioNeural")
        saved_female = config.get("BOT_VOICE_FEMALE", "es_MX-DaliaNeural")
        
        self.voice_male_var = ctk.StringVar(value=saved_male)
        self.voice_male_menu = ctk.CTkOptionMenu(cmd_frame, values=self.voices_male,
                                              variable=self.voice_male_var,
                                              fg_color=CARD, button_color=BORD, dropdown_fg_color=CARD2,
                                              text_color=TXT, font=("Arial", 11))
        self.voice_male_menu.pack(fill="x", padx=10, pady=(0, 6))

        self.voice_female_var = ctk.StringVar(value=saved_female)
        self.voice_female_menu = ctk.CTkOptionMenu(cmd_frame, values=self.voices_female,
                                                    variable=self.voice_female_var,
                                                    fg_color=CARD, button_color=BORD, dropdown_fg_color=CARD2,
                                                    text_color=TXT, font=("Arial", 11))
        self.voice_female_menu.pack(fill="x", padx=10, pady=(0, 6))

        btn_frame = ctk.CTkFrame(c, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(btn_frame, text="💾 Guardar comandos", fg_color=GRN, text_color=GRN_T,
                     height=30, corner_radius=8, hover_color="#22c55e",
                     command=self._guardar_bot_cmds).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(btn_frame, text="🧪 Test", fg_color=PURP, text_color="#e9d5ff",
                     height=30, corner_radius=8,
                     command=self._test_bot_speaker).pack(side="left", fill="x", expand=True, padx=(4, 0))

        inf = mk(c, fg_color=CARD2)
        inf.pack(fill="x", padx=10, pady=(0, 10))
        lb(inf, "ℹ  Uso:", sz=11, bold=True).pack(anchor="w", padx=10, pady=(8, 2))
        lb(inf, "• !sp <mensaje> — El bot dice el mensaje\n"
                "• !spm <audio> — Reproduce audio local",
           sz=10, col=MUT, justify="left").pack(anchor="w", padx=10, pady=(0, 10))

        return tab

    # ════════════════════════════════════════════════════════════════════════
    #  TAB API_KEY
    # ════════════════════════════════════════════════════════════════════════
    def _tab_api_key(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🔑  API Keys", sz=13, bold=True).pack(anchor="w", padx=10, pady=(12, 4))

        # === GROQ - Traductor, Vision, Comentarista ===
        groq_frame = mk(c, fg_color=CARD2)
        groq_frame.pack(fill="x", padx=10, pady=(0, 8))
        lb(groq_frame, "🔵 Groq — Traductor, Vision, Comentarista", sz=12, col=TXT, bold=True).pack(anchor="w", padx=10, pady=(10, 4))

        self.groq_key_entry = ctk.CTkEntry(groq_frame, placeholder_text="gsk_...",
                                          font=("Consolas", 12), show="*",
                                          fg_color=CARD, text_color=TXT, border_color=BORD)
        self.groq_key_entry.pack(fill="x", padx=10, pady=(0, 6))
        groq_val = config.get("GROQ_API_KEY", "")
        if groq_val:
            self.groq_key_entry.insert(0, groq_val)

        btn_g = ctk.CTkFrame(groq_frame, fg_color="transparent")
        btn_g.pack(fill="x", padx=10, pady=(0, 8))
        btn_g.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(btn_g, text="👁", fg_color=CARD, text_color=TXT,
                      command=lambda: self._toggle_key(self.groq_key_entry),
                      height=30, corner_radius=6, width=40).grid(row=0, column=0, padx=(0, 4))
        ctk.CTkButton(btn_g, text="💾 Guardar", fg_color=GRN, text_color=GRN_T,
                      command=lambda: self._guardar_groq(),
                      height=30, corner_radius=6, hover_color="#22c55e").grid(row=0, column=1, padx=2)
        ctk.CTkButton(btn_g, text="🧪 Test", fg_color=PURP, text_color="#e9d5ff",
                      command=lambda: self._test_api("groq", self.groq_key_entry.get()),
                      height=30, corner_radius=6).grid(row=0, column=2, padx=(4, 0))

        link_g = lb(groq_frame, "🌐 https://console.groq.com/keys", sz=10, col="#93c5fd", cursor="hand2")
        link_g.pack(anchor="w", padx=10, pady=(0, 6))
        link_g.bind("<Button-1>", lambda e: webbrowser.open("https://console.groq.com/keys"))

        groq_status = config.get("GROQ_API_KEY", "")
        if groq_status and len(groq_status) > 5:
            lb(groq_frame, f"✅ Guardada (****{groq_status[-6:]})", sz=10, col=GRN_T).pack(anchor="w", padx=10, pady=(0, 8))
        else:
            lb(groq_frame, "❌ No configurada", sz=10, col=RED_T).pack(anchor="w", padx=10, pady=(0, 8))

        # === CEREBRAS - Chat Bot ===
        cb_frame = mk(c, fg_color=CARD2)
        cb_frame.pack(fill="x", padx=10, pady=(0, 8))
        lb(cb_frame, "🟡 Cerebras — Chat Bot, PTT, Twitch", sz=12, col=TXT, bold=True).pack(anchor="w", padx=10, pady=(10, 4))

        self.cere_key_entry = ctk.CTkEntry(cb_frame, placeholder_text="csk_...",
                                           font=("Consolas", 12), show="*",
                                           fg_color=CARD, text_color=TXT, border_color=BORD)
        self.cere_key_entry.pack(fill="x", padx=10, pady=(0, 6))
        cere_val = config.get("CEREBRAS_API_KEY", "")
        if cere_val:
            self.cere_key_entry.insert(0, cere_val)

        btn_c = ctk.CTkFrame(cb_frame, fg_color="transparent")
        btn_c.pack(fill="x", padx=10, pady=(0, 8))
        btn_c.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(btn_c, text="👁", fg_color=CARD, text_color=TXT,
                      command=lambda: self._toggle_key(self.cere_key_entry),
                      height=30, corner_radius=6, width=40).grid(row=0, column=0, padx=(0, 4))
        ctk.CTkButton(btn_c, text="💾 Guardar", fg_color=GRN, text_color=GRN_T,
                      command=lambda: self._guardar_cere(),
                      height=30, corner_radius=6, hover_color="#22c55e").grid(row=0, column=1, padx=2)
        ctk.CTkButton(btn_c, text="🧪 Test", fg_color=PURP, text_color="#e9d5ff",
                      command=lambda: self._test_api("cerebras", self.cere_key_entry.get()),
                      height=30, corner_radius=6).grid(row=0, column=2, padx=(4, 0))

        link_c = lb(cb_frame, "🌐 https://cloud.cerebras.ai", sz=10, col="#93c5fd", cursor="hand2")
        link_c.pack(anchor="w", padx=10, pady=(0, 6))
        link_c.bind("<Button-1>", lambda e: webbrowser.open("https://cloud.cerebras.ai"))

        cere_status = config.get("CEREBRAS_API_KEY", "")
        if cere_status and len(cere_status) > 5:
            lb(cb_frame, f"✅ Guardada (****{cere_status[-6:]})", sz=10, col=GRN_T).pack(anchor="w", padx=10, pady=(0, 8))
        else:
            lb(cb_frame, "❌ No configurada", sz=10, col=RED_T).pack(anchor="w", padx=10, pady=(0, 8))

        # === GOOGLE AI ===
        google_frame = mk(c, fg_color=CARD2)
        google_frame.pack(fill="x", padx=10, pady=(0, 8))
        lb(google_frame, "🔴 Google AI Studio", sz=12, col=TXT, bold=True).pack(anchor="w", padx=10, pady=(10, 4))

        self.google_key_entry = ctk.CTkEntry(google_frame, placeholder_text="AIza...",
                                             font=("Consolas", 12), show="*",
                                             fg_color=CARD, text_color=TXT, border_color=BORD)
        self.google_key_entry.pack(fill="x", padx=10, pady=(0, 6))
        google_val = config.get("GOOGLE_API_KEY", "")
        if google_val:
            self.google_key_entry.insert(0, google_val)

        btn_goog = ctk.CTkFrame(google_frame, fg_color="transparent")
        btn_goog.pack(fill="x", padx=10, pady=(0, 8))
        btn_goog.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(btn_goog, text="👁", fg_color=CARD, text_color=TXT,
                      command=lambda: self._toggle_key(self.google_key_entry),
                      height=30, corner_radius=6, width=40).grid(row=0, column=0, padx=(0, 4))
        ctk.CTkButton(btn_goog, text="💾 Guardar", fg_color=GRN, text_color=GRN_T,
                      command=lambda: self._guardar_google(),
                      height=30, corner_radius=6, hover_color="#22c55e").grid(row=0, column=1, padx=2)
        ctk.CTkButton(btn_goog, text="🧪 Test", fg_color=PURP, text_color="#e9d5ff",
                      command=lambda: self._test_api("google", self.google_key_entry.get()),
                      height=30, corner_radius=6).grid(row=0, column=2, padx=(4, 0))

        link_goog = lb(google_frame, "🌐 https://aistudio.google.com/apikey", sz=10, col="#93c5fd", cursor="hand2")
        link_goog.pack(anchor="w", padx=10, pady=(0, 6))
        link_goog.bind("<Button-1>", lambda e: webbrowser.open("https://aistudio.google.com/apikey"))

        google_status = config.get("GOOGLE_API_KEY", "")
        if google_status and len(google_status) > 5:
            lb(google_frame, f"✅ Guardada (****{google_status[-6:]})", sz=10, col=GRN_T).pack(anchor="w", padx=10, pady=(0, 8))
        else:
            lb(google_frame, "❌ No configurada", sz=10, col=RED_T).pack(anchor="w", padx=10, pady=(0, 8))

        return tab

    def _toggle_key(self, entry):
        current = entry.cget("show")
        entry.configure(show="" if current == "*" else "*")

    def _guardar_groq(self):
        value = self.groq_key_entry.get().strip()
        if not value:
            self.log("❌  Ingresa una API Key válida")
            return
        if not value.startswith("gsk_"):
            self.log("❌  Groq API Key debe empezar con 'gsk_'")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["GROQ_API_KEY"] = value
        save_config(cfg)
        config["GROQ_API_KEY"] = value
        self.log(f"✅  GROQ_API_KEY guardada correctamente")

    def _guardar_bot_cmds(self):
        cmd = self.cmd_speak_entry.get().strip()
        cmd_map = self.cmd_speakmap_entry.get().strip()
        voice_male = self.voice_male_var.get()
        voice_female = self.voice_female_var.get()
        if not cmd:
            self.log("❌  Ingresa el comando Speak")
            return
        if not cmd_map:
            self.log("❌  Ingresa el comando SpeakMap")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["BOT_SPEAK_CMD"] = cmd
        cfg["BOT_SPEAKMAP_CMD"] = cmd_map
        cfg["BOT_VOICE_MALE"] = voice_male
        cfg["BOT_VOICE_FEMALE"] = voice_female
        save_config(cfg)
        config["BOT_SPEAK_CMD"] = cmd
        config["BOT_SPEAKMAP_CMD"] = cmd_map
        config["BOT_VOICE_MALE"] = voice_male
        config["BOT_VOICE_FEMALE"] = voice_female
        self.log(f"✅  Guardado: {cmd} ({voice_male}), {cmd_map} ({voice_female})")

    def _test_bot_speaker(self):
        """Test the selected Bot Speaker voices"""
        voice_male_display = self.voice_male_var.get()
        voice_female_display = self.voice_female_var.get()
        
        voice_male_display = self.voice_male_var.get()
        voice_female_display = self.voice_female_var.get()
        voice_male_edge = voice_male_display.replace("_", "-")
        voice_female_edge = voice_female_display.replace("_", "-")
        
        _, device_id = self.get_devices()
        
        self.log("Probando voz masculina...")
        speak("Hola, esta es una prueba de voz masculina", voice_male_edge, device_id)
        
        import time
        time.sleep(1)
        
        self.log("Probando voz femenina...")
        speak("Hola, esta es una prueba de voz femenina", voice_female_edge, device_id)

    def _test_ia_voice(self):
        """Test the selected IA voice"""
        voice = self.ia_voice_var.get()
        command = self.ia_command_entry.get().strip() or "!IA"
        if not voice:
            self.log("Selecciona una voz para probar")
            return
        
        voice_edge = voice.replace("_", "-")
        
        self.log(f"Probando voz IA: {voice}")
        test_text = "Hola, esta es una prueba de la voz del Bot Chat IA"
        _, device_id = self.get_devices()
        speak(test_text, voice_edge, device_id)

    def _guardar_voice_default(self):
        voice = self.voice_default_var.get()
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["BOT_VOICE_DEFAULT"] = voice
        save_config(cfg)
        config["BOT_VOICE_DEFAULT"] = voice
        self.log(f"✅  Voz por defecto: {voice}")

    def _guardar_ia_config(self):
        command = self.ia_command_entry.get().strip()
        voice = self.ia_voice_var.get()
        if not command:
            self.log("❌  Ingresa el comando IA")
            return
        if not command.startswith("!"):
            self.log("❌  El comando IA debe comenzar con '!'")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["BOT_IA_COMMAND"] = command
        cfg["BOT_IA_VOICE"] = voice
        cfg["COMENTARISTA_LEER_CHAT"] = self.comentarista_leer_chat.get()
        save_config(cfg)
        config["BOT_IA_COMMAND"] = command
        config["BOT_IA_VOICE"] = voice
        config["COMENTARISTA_LEER_CHAT"] = self.comentarista_leer_chat.get()
        self._ia_command = command
        self._ia_voice = voice
        chat_str = "ON" if self.comentarista_leer_chat.get() else "OFF"
        self.log(f"✅  Guardado IA: {command} ({voice}) | Chat Twitch: {chat_str}")

    def _guardar_eq(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["EQ_BASS"] = self.bass_var.get()
        cfg["EQ_TREBLE"] = self.treble_var.get()
        cfg["EQ_SPEED"] = self.speed_var.get()
        cfg["EQ_AUTOTUNE"] = self.autotune_var.get()
        save_config(cfg)
        config["EQ_BASS"] = self.bass_var.get()
        config["EQ_TREBLE"] = self.treble_var.get()
        config["EQ_SPEED"] = self.speed_var.get()
        config["EQ_AUTOTUNE"] = self.autotune_var.get()
        self.log(f"✅  EQ: Graves={self.bass_var.get()}, Agudos={self.treble_var.get()}, Vel={self.speed_var.get()}%, Auto-Tune={self.autotune_var.get()}%")

    def _guardar_cere(self):
        value = self.cere_key_entry.get().strip()
        if not value:
            self.log("❌  Ingresa una API Key válida")
            return
        if not (value.startswith("csk-") or value.startswith("csk_")):
            self.log("❌  Cerebras API Key debe empezar con 'csk-'")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["CEREBRAS_API_KEY"] = value
        save_config(cfg)
        config["CEREBRAS_API_KEY"] = value
        self.log(f"✅  CEREBRAS_API_KEY guardada correctamente")

    def _guardar_google(self):
        value = self.google_key_entry.get().strip()
        if not value:
            self.log("❌  Ingresa una API Key válida")
            return
        if not value.startswith("AIza"):
            self.log("❌  Google API Key debe empezar con 'AIza'")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["GOOGLE_API_KEY"] = value
        save_config(cfg)
        config["GOOGLE_API_KEY"] = value
        self.log(f"GOOGLE_API_KEY guardada correctamente")

    def _test_api(self, provider, api_key):
        if not api_key:
            self.log(f"Primero guarda la API Key")
            return
        self.log(f"Probando {provider}...")
        threading.Thread(target=self._test_api_thread, args=(provider, api_key), daemon=True).start()

    def _test_api_thread(self, provider, api_key):
        try:
            if provider == "groq":
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                                  headers={"Authorization": f"Bearer {api_key}"},
                                  json={"model": "llama-3.1-8b-instant",
                                        "messages": [{"role": "user", "content": "hola"}],
                                        "max_tokens": 10}, timeout=10)
            elif provider == "cerebras":
                r = requests.post("https://api.cerebras.ai/v1/chat/completions",
                                   headers={"Authorization": f"Bearer {api_key}"},
                                   json={"model": "llama3.1-8b",
                                         "messages": [{"role": "user", "content": "hola"}],
                                         "max_tokens": 10}, timeout=10)
            elif provider == "google":
                if not api_key.startswith("AIza"):
                    self.log("❌  Google API Key debe empezar con 'AIza'")
                    return
                self.log(f"✅  Google API Key válida (****{api_key[-6:]})")
                return
            if r.status_code == 200:
                self.log(f"✅  {provider} funcionando correctamente")
            else:
                self.log(f"❌  {provider} error: {r.status_code}")
        except Exception as e:
            self.log(f"❌  {provider} error: {e}")

    def _tab_game_ia(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        
        # Título
        lb(c, "🎮 Game IA", sz=16, bold=True, col="#ff69b4").pack(anchor="w", padx=10, pady=(10, 4))
        lb(c, "IA que juega automáticamente en juegos", sz=11, col=MUT).pack(anchor="w", padx=10, pady=(0, 6))
        
        # Modo de jugador
        mode_frame = mk(tab, fg_color=CARD2)
        mode_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(mode_frame, "👤 Modo de Jugador:", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        
        self.game_player_mode = ctk.StringVar(value="player1")
        
        ctk.CTkRadioButton(mode_frame, text="Player 1 (Yo)", variable=self.game_player_mode, 
                          value="player1", fg_color=GRN, text_color=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        ctk.CTkRadioButton(mode_frame, text="Player 2 (Contrario)", variable=self.game_player_mode,
                          value="player2", fg_color=RED, text_color=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        
        # Captura de pantalla
        capture_frame = mk(tab, fg_color=CARD2)
        capture_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(capture_frame, "📷 Captura de Pantalla", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        
        btn_capture = ctk.CTkButton(capture_frame, text="📸 Capturar Pantalla", fg_color=CARD, text_color=TXT,
                                    height=32, corner_radius=8, command=self._capture_screen)
        btn_capture.pack(fill="x", padx=10, pady=(4, 4))
        
        # Controles
        control_frame = mk(tab, fg_color=CARD2)
        control_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(control_frame, "🎯 Controles", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        
        btn_start = ctk.CTkButton(control_frame, text="▶ Iniciar Game IA", fg_color=GRN, text_color=GRN_T,
                                   height=36, corner_radius=8, hover_color="#22c55e", command=self._start_game_ia)
        btn_start.pack(fill="x", padx=10, pady=(4, 4))
        
        btn_stop = ctk.CTkButton(control_frame, text="⏹ Detener Game IA", fg_color=RED, text_color="#fff",
                               height=36, corner_radius=8, hover_color="#dc2626", command=self._stop_game_ia)
        btn_stop.pack(fill="x", padx=10, pady=(4, 4))
        
        # Estado
        status_frame = mk(tab, fg_color=CARD2)
        status_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(status_frame, "📊 Estado:", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        self.game_status_lbl = lb(status_frame, "⏸ Detenido", sz=11, col=RED_T)
        self.game_status_lbl.pack(anchor="w", padx=10, pady=(0, 4))
        
        # Tips
        tips_frame = mk(tab, fg_color=CARD2)
        tips_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(tips_frame, "💡 Tips:", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        lb(tips_frame, "  1. Abre el juego en tu PC", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(tips_frame, "  2. Selecciona Player 1 o Player 2", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(tips_frame, "  3. Presiona 'Capturar' para ver pantalla", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(tips_frame, "  4. Presiona 'Iniciar' para que IA juegue", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        
        return tab

    def _capture_screen(self):
        """Mostrar análisis de pantalla del servicio de visión"""
        try:
            analysis = vision_service.get_analysis()
            text = analysis.get("text", "")
            desc = analysis.get("description", "")
            game_state = analysis.get("game_state", "")
            objects = analysis.get("objects", [])
            
            result = f"📊 Análisis de pantalla:\n"
            if text.strip():
                result += f"📝 Texto: {text[:100]}{'...' if len(text) > 100 else ''}\n"
            if desc.strip():
                result += f"👁 Descripción: {desc[:100]}{'...' if len(desc) > 100 else ''}\n"
            if game_state.strip():
                result += f"🎮 Estado juego: {game_state}\n"
            if objects:
                result += f"🎯 Objetos: {', '.join(objects[:5])}{'...' if len(objects) > 5 else ''}\n"
            
            self.log(result if result.strip() != "📊 Análisis de pantalla:" else "⏳ Esperando análisis inicial...")
        except Exception as e:
            self.log(f"❌ Error en análisis: {e}")

    def _start_game_ia(self):
        """Iniciar IA usando servicio de visión"""
        try:
            # Forzar un análisis inmediato para tener datos iniciales
            vision_service._analyze_screen()
            
            mode = self.game_player_mode.get()
            self.game_status_lbl.configure(text=f"▶ Jugando como {mode}", col=GRN_T)
            self.log(f"🎮 Game IA iniciado: {mode}")
            
            # Hilo para jugar usando visión
            def game_loop():
                import time
                last_analysis_time = 0
                while hasattr(self, '_game_ia_running') and self._game_ia_running:
                    try:
                        # Actualizar análisis cada 2 segundos para reducir carga
                        current_time = time.time()
                        if current_time - last_analysis_time >= 2.0:
                            vision_service._analyze_screen()
                            last_analysis_time = current_time
                        
                        # Obtener estado del juego del servicio de visión
                        analysis = vision_service.get_analysis()
                        game_state = analysis.get("game_state", "")
                        
                        # En modo simple, hacer click basado en análisis básico
                        # En una implementación más avanzada, esto usaría el game_state para decisiones inteligentes
                        if game_state and "click" in game_state.lower():
                            # Simular un click en el centro si detectamos que hay algo para hacer click
                            import pyautogui
                            screen_width, screen_height = pyautogui.size()
                            x, y = screen_width // 2, screen_height // 2
                            pyautogui.click(x, y)
                            self.wlog(f"🖱 Click vision en ({x}, {y}) basado en estado: {game_state[:50]}")
                        elif not game_state or len(game_state.strip()) < 10:
                            # Si no hay estado claro, hacer click aleatorio suave para testing
                            import random
                            import pyautogui
                            screen_width, screen_height = pyautogui.size()
                            x = random.randint(screen_width//4, 3*screen_width//4)
                            y = random.randint(screen_height//4, 3*screen_height//4)
                            pyautogui.click(x, y)
                            self.wlog(f"🖱 Click aleatorio en ({x}, {y}) - esperando análisis...")
                        
                        time.sleep(1.5)  # Menos frecuente para reducir CPU
                    except Exception as e:
                        self.wlog(f"❌ Error en bucle de juego: {e}")
                        time.sleep(2)
            
            self._game_ia_running = True
            threading.Thread(target=game_loop, daemon=True).start()
        except Exception as e:
            self.log(f"❌ Error: {e}")

    def _stop_game_ia(self):
        """Detener IA"""
        try:
            self._game_ia_running = False
            self.game_status_lbl.configure(text="⏸ Detenido", col=RED_T)
            self.log("⏹ Game IA detenido")
        except Exception as e:
            self.log(f"❌ Error: {e}")

    def _tab_creditos(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        
        # Título con versión
        lb(c, f"📋 {APP_NAME}", sz=18, bold=True, col="#ff69b4").pack(anchor="w", padx=10, pady=(10, 4))
        lb(c, f"Versión {APP_VERSION}", sz=12, col=MUT).pack(anchor="w", padx=10, pady=(0, 10))
        
        # Descripción
        desc_frame = mk(tab, fg_color=CARD2)
        desc_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(desc_frame, "🎤 Asistente VTuber con IA", sz=13, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        lb(desc_frame, "Bot de Twitch con Chat IA, traductor en tiempo real, voz PTT y más.", sz=11, col=MUT).pack(anchor="w", padx=10, pady=(0, 4))
        
        # Características
        feat_frame = mk(tab, fg_color=CARD2)
        feat_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(feat_frame, "✨ Características", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        features = [
            "🤖 Chat IA con Cerebras/Groq",
            "🔊 Voces Edge TTS neurales",
            "🎛 Equalizador de voz (graves, agudos, velocidad, auto-tune)",
            "😀 Detección de emociones",
            "🌍 Traductor en tiempo real",
            "🎤 Voz PTT con Vosk",
            "📺 Monitor de juego",
            "🎮 Game watcher",
        ]
        for f in features:
            lb(feat_frame, f"  • {f}", sz=11, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        
        # Créditos
        cred_frame = mk(tab, fg_color=CARD2)
        cred_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(cred_frame, "📌 Créditos", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        lb(cred_frame, "  Desarrollado por Manuel0084", sz=11, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(cred_frame, "  GitHub: github.com/manuel00084", sz=11, col="#93c5fd", cursor="hand2").pack(anchor="w", padx=10, pady=(2, 0))
        
        # Aviso legal
        legal_frame = mk(tab, fg_color=CARD2)
        legal_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(legal_frame, "⚖️ Licencia", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        
        lb(legal_frame, "  Licensed under the Apache License, Version 2.0", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        apache_link = lb(legal_frame, "  http://www.apache.org/licenses/LICENSE-2.0", sz=10, col="#93c5fd", cursor="hand2")
        apache_link.pack(anchor="w", padx=10, pady=(2, 0))
        apache_link.bind("<Button-1>", lambda e: webbrowser.open("http://www.apache.org/licenses/LICENSE-2.0"))
        
        lb(legal_frame, "", sz=10).pack(anchor="w", padx=10, pady=(4, 0))
        lb(legal_frame, "  Copyright 2024 Manuel0084", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        
        # Términos legales completos
        terms_frame = mk(tab, fg_color=CARD2)
        terms_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        lb(terms_frame, "📜 Términos Legales", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        
        terms_text = """Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

1. Definitions.
"License" shall mean the terms and conditions for use, reproduction, and distribution as defined by Sections 1 through 9 of this document.
"Licensor" shall mean the copyright owner or entity authorized by the copyright owner that is granting the License.
"You" (or "Your") shall mean an individual or Legal Entity exercising permissions granted by this License.
"Work" shall mean the work of authorship, whether in Source or Object form, made available under the License.
"Derivative Works" shall mean any work, whether in Source or Object form, that is based on (or derived from) the Work.

2. Grant of Copyright License.
Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute the Work.

3. Grant of Patent License.
Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable patent license.

4. Redistribution.
You may reproduce and distribute copies of the Work or Derivative Works thereof in any medium, with or without modifications, provided that You meet the following conditions:
(a) You must give any other recipients of the Work or Derivative Works a copy of this License; and
(b) You must cause any modified files to carry prominent notices stating that You changed the files.

5. Submission of Contributions.
Unless You explicitly state otherwise, any Contribution intentionally submitted for inclusion in the Work by You to the Licensor shall be under the terms and conditions of this License.

6. Trademarks.
This License does not grant permission to use the trade names, trademarks, service marks, or product names of the Licensor.

7. Disclaimer of Warranty.
Unless required by applicable law or agreed to in writing, Licensor provides the Work on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

8. Limitation of Liability.
In no event and under no legal theory, whether in tort (including negligence), contract, or otherwise, shall any Contributor be liable to You for damages.

9. Accepting Warranty or Additional Liability.
While redistributing the Work, You may choose to offer, and charge a fee for, acceptance of support, warranty, indemnity, or other liability obligations.

END OF TERMS AND CONDITIONS"""
        
        terms_box = ctk.CTkTextbox(terms_frame, fg_color=BG, text_color=TXT, font=("Consolas", 9))
        terms_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        terms_box.insert("1.0", terms_text)
        terms_box.configure(state="disabled")
        
        # Third Party Licenses
        third_party_frame = mk(tab, fg_color=CARD2)
        third_party_frame.pack(fill="x", padx=14, pady=(0, 8))
        lb(third_party_frame, "📦 Third Party Licenses", sz=12, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(10, 4))
        
        lb(third_party_frame, "Este proyecto utiliza software y modelos de terceros.", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "", sz=10).pack(anchor="w", padx=10, pady=(2, 0))
        
        lb(third_party_frame, "Vosk", sz=11, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "  Proyecto: https://alphacephei.com/vosk/", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "  Licencia: Apache 2.0", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        
        lb(third_party_frame, "", sz=10).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "Otros componentes", sz=11, bold=True, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "  Cada librería y modelo mantiene su licencia original.", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        
        lb(third_party_frame, "  Edge TTS - Microsoft", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "  CustomTkinter - MIT", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "  TwitchIO - MIT", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(third_party_frame, "  Groq/Cerebras API - Proprietary", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        
        return tab

    # ═════════════════════════════��══════════════════════════════════════════
    #  LÓGICA
    # ════════════════════════════════════════════════════════════════════════
    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def wlog(self, text):
        self.log(text)

    def get_devices(self):
        sn = self.sp2.get()
        an = self.ia2.get()
        mn = self.mn2.get()
        sid = next((i for n, i in self.devices if n == sn), 0)
        iid = next((i for n, i in self.devices if n == an), 0)
        if mn in ("(Ninguno)", ""):
            return sid, iid
        mid = next((i for n, i in self.devices if n == mn), None)
        return sid, ([iid, mid] if mid and mid != iid else iid)

    def change_mode(self, filename):
        # Guardar el prompt seleccionado en config.txt
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["SELECTED_PROMPT"] = filename
        save_config(cfg)
        config["SELECTED_PROMPT"] = filename
        # Cargar el nuevo prompt
        with open(os.path.join(self.prompt_folder, filename), encoding="utf-8") as f:
            self.current_prompt = f.read()
        self.log(f"Personalidad cambiada a: {filename}")
    
    def _crear_nuevo_prompt(self):
        # Pedir nombre para el nuevo prompt
        dialog = ctk.CTkInputDialog(title="Nueva Personalidad", 
                                    text="Ingresa el nombre para la nueva personalidad:")
        nombre = dialog.get_input()
        if nombre:
            # Validar nombre de archivo
            nombre = nombre.strip()
            if not nombre.endswith(".txt"):
                nombre += ".txt"
            
            # Verificar que no exista
            if nombre in self.prompt_files:
                self.log(f"Ya existe una personalidad con ese nombre")
                return
            
            # Crear el archivo con contenido por defecto
            try:
                ruta = os.path.join(self.prompt_folder, nombre)
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write("Eres una VTuber divertida y amigable.")
                
                # Actualizar la lista de prompts
                self.prompt_files = [f for f in os.listdir(self.prompt_folder) if f.endswith(".txt")]
                self.prompt_files.sort()
                
                # Actualizar el dropdown
                self.mode_select.configure(values=self.prompt_files)
                self.mode_select.set(nombre)
                
                # Guardar la selección
                from src.core.config import load_config, save_config
                cfg = load_config()
                cfg["SELECTED_PROMPT"] = nombre
                save_config(cfg)
                config["SELECTED_PROMPT"] = nombre
                
                # Cargar el nuevo prompt
                with open(ruta, encoding="utf-8") as f:
                    self.current_prompt = f.read()
                
                self.log(f"Nueva personalidad '{nombre}' creada")
            except Exception as e:
                self.log(f"Error al crear personalidad: {e}")

    def test_voice(self):
        stop_audio()
        _, d = self.get_devices()
        speak("Hola, prueba de voz", "es-ES-AlvaroNeural", d)

    def test_ia(self):
        def run():
            stop_audio()
            api_key = config.get("CEREBRAS_API_KEY", "")
            if not api_key:
                self.log("❌  Falta CEREBRAS_API_KEY")
                return
            r = ask_ai("Di algo como VTuber", api_key, self.current_prompt, "cerebras")
            self.log(f"🤖  Cerebras: {r}")
            _, d = self.get_devices()
            speak(r, "es-MX-DaliaNeural", d)
        threading.Thread(target=run, daemon=True).start()

    def ptt_click(self):
        def run():
            try:
                from src.audio.stt import listen
                stop_audio(); self.log("🎤  Escuchando...")
                text = listen()
                if not text: self.log("❌  No se entendió"); return
                self.log(f"🗣  Tú: {text}")
                api_key = config.get("CEREBRAS_API_KEY", "")
                if not api_key:
                    self.log("❌  Falta CEREBRAS_API_KEY"); return
                r = ask_ai(text, api_key, self.current_prompt, "cerebras")
                self.log(f"🤖  IA: {r}")
                _, d = self.get_devices()
                speak(r, "es-MX-DaliaNeural", d)
            except Exception as e:
                self.log(f"❌  PTT: {e}")
        threading.Thread(target=run, daemon=True).start()

    # ════════════════════════════════════════════════════════════════════════
    #  TWITCH — Conexión con OAuth (FIX)
    # ════════════════════════════════════════════════════════════════════════
    def connect_twitch(self):
        """
        Si ya hay TWITCH_TOKEN en config -> arranca el chat directo.
        Si NO hay token -> abre el navegador para autorizar (OAuth) y al
        recibir el callback recarga la config y arranca el chat.
        """
        def _start_chat_with_current_config():
            # Recargar config para obtener los valores actualizados
            from src.core.config import load_config
            cfg = load_config()
            
            tok = cfg.get("TWITCH_TOKEN", "")
            nick = cfg.get("NICK", "")
            chan = cfg.get("CHANNEL", "")
            
            if not tok or not nick or not chan:
                self.log("Faltan datos tras OAuth (TOKEN/NICK/CHANNEL)")
                return
            sd, idev = self.get_devices()
            start_chat(self, tok, nick, chan,
                       cfg.get("GROQ_API_KEY", ""), sd, idev, self)
            self.after(0, lambda: (
                self.twitch_btn.configure(text="Conectado",
                                          fg_color=GRN, text_color=GRN_T),
            ))

        def _on_oauth_success(token, nick, channel):
            self.log(f"✅  OAuth OK — usuario: {nick}")
            # Recargar config.txt (oauth_server ya lo guardó)
            try:
                from src.core.config import load_config
                fresh = load_config()
                config.update(fresh)
            except Exception as e:
                self.log(f"⚠  No se pudo recargar config: {e}")
            _start_chat_with_current_config()

        def _on_oauth_error(msg):
            self.log(f"❌  OAuth: {msg}")
            self.after(0, lambda: self.twitch_btn.configure(
                text="🟣  Conectar Twitch", fg_color=PURP, text_color="#fff"))

        def run():
            tok = config.get("TWITCH_TOKEN", "")
            if tok:
                self.log("🔍  Validando token de Twitch...")
                if not validate_token(tok):
                    self.log("⚠  Token expirado o inválido. Abriendo OAuth...")
                    self.after(0, lambda: self.twitch_btn.configure(
                        text="🟣  Autorizando...",
                        fg_color=AMB, text_color=AMB_T))
                    # Limpiar token inválido
                    from src.core.oauth_server import clear_token_file
                    clear_token_file()
                    tok = None
                else:
                    self.log("🟣  Conectando Twitch con token guardado...")
                    _start_chat_with_current_config()
                    return

            # No hay token -> flujo OAuth
            if TwitchOAuth is None:
                self.log("❌  oauth_server no disponible (revisa secrets_manager.py)")
                return
            self.log("🌐  Abriendo navegador para autorizar en Twitch...")
            self.after(0, lambda: self.twitch_btn.configure(
                text="🟣  Esperando autorización...",
                fg_color=AMB, text_color=AMB_T))
            try:
                TwitchOAuth(on_success=_on_oauth_success,
                            on_error=_on_oauth_error).start()
            except Exception as e:
                self.log(f"❌  No se pudo iniciar OAuth: {e}")
                self.log(traceback.format_exc())

        threading.Thread(target=run, daemon=True).start()

    # ── Comentarista ─────────────────────────────────────────────────────────
    def toggle_watcher(self, event=None):
        if self.comentarista_activo.get() and (not self.game_watcher or not self.game_watcher.activo):
            if not GW_OK:
                self.log("❌  game_watcher.py no disponible — pip install pillow")
                self.comentarista_activo.set(False)
                return
            groq_key = config.get("GROQ_API_KEY", "")
            google_key = config.get("GOOGLE_API_KEY", "")
            if not groq_key and not google_key:
                self.log("❌  Falta GROQ_API_KEY o GOOGLE_API_KEY")
                self.comentarista_activo.set(False)
                return
            leer_chat = self.comentarista_leer_chat.get()
            self.game_watcher = GameWatcher(
                api_key=groq_key,
                google_api_key=google_key,
                speak_fn=speak, stop_audio_fn=stop_audio,
                get_devices_fn=self.get_devices,
                current_prompt_fn=lambda: self.current_prompt,
                intervalo=30, voice="es-MX-DaliaNeural",
                log_fn=self.log, modo_solo_ver=False,
                get_twitch_messages_fn=get_twitch_messages,
                leer_chat=leer_chat)
            self.game_watcher.iniciar()
            chat_str = " + CHAT" if leer_chat else ""
            self.log(f"🎮 Comentarista INICIADO{chat_str}")
        elif not self.comentarista_activo.get() and self.game_watcher and self.game_watcher.activo:
            self.game_watcher.detener()
            self.game_watcher = None
            self.log("🎮 Comentarista DETENIDO")

    # ── Traductor ─────────────────────────────────────────────────────────────
    def _get_translator(self):
        motor = self.trad_motor.get()
        if self.translator is None:
            self.translator = TranslatorManager(
                master=self, api_key=config.get("GROQ_API_KEY", ""),
                speak_fn=speak, stop_audio_fn=stop_audio,
                get_devices_fn=self.get_devices, voice="es-MX-DaliaNeural",
                idioma_destino=self.idioma_var.get(), log_fn=self.log,
                leer_en_voz=self.leer_voz_var.get(), motor=motor)
        else:
            self.translator.idioma_destino = self.idioma_var.get()
            self.translator.leer_en_voz    = self.leer_voz_var.get()
            self.translator.motor          = motor
        self.translator.intervalo = int(self.trad_intervalo_var.get())
        return self.translator

    def _guardar_config_panel(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        
        # Guardar la personalidad seleccionada
        if hasattr(self, 'mode_select'):
            cfg["SELECTED_PROMPT"] = self.mode_select.get()
        
        if hasattr(self, 'sp2'):
            idx = self.sp2.get()
            try:
                cfg["SPEAKER_DEVICE"] = str(self.dev_names.index(idx)) if idx in self.dev_names else "0"
            except:
                cfg["SPEAKER_DEVICE"] = "0"
        if hasattr(self, 'ia2'):
            idx = self.ia2.get()
            try:
                cfg["IA_DEVICE"] = str(self.dev_names.index(idx) if idx in self.dev_names else 0)
            except:
                cfg["IA_DEVICE"] = "0"
        
        # Guardar tecla PTT
        if hasattr(self, 'ptt_key_entry'):
            ptt_key = self.ptt_key_entry.get().strip().upper()
            if not ptt_key:
                ptt_key = "F9"
            cfg["PTT_KEY"] = ptt_key
            config["PTT_KEY"] = ptt_key
        
        save_config(cfg)
        self.log(f"Configuracion guardada ({ptt_key if hasattr(self, 'ptt_key_entry') else 'F9'})")

    def _borrar_memoria(self):
        try:
            from src.ai.memory import clear_memory
            clear_memory()
            self.log("🗑  Memoria borrada correctamente")
        except Exception as e:
            self.log(f"❌  Error al borrar memoria: {e}")

    def trad_area_unica(self):
        t = self._get_translator()
        if t: self.log("📐  Dibuja área..."); t.seleccionar_area_y_traducir()

    def trad_pantalla_unica(self):
        t = self._get_translator()
        if t: self.log("🖥  Traduciendo..."); t.traducir_ahora(bbox=None)

    def trad_continuo_area(self):
        t = self._get_translator()
        if t:
            if t.activo: self.log("⚠  Ya hay traducción activa"); return
            self.log("📐  Dibuja área continua...")
            t.seleccionar_area_continuo(); self.btn_detener_trad.configure(state="normal")

    def trad_continuo_full(self):
        t = self._get_translator()
        if t:
            if t.activo: self.log("⚠  Ya hay traducción activa"); return
            t.area_fija = None; t.iniciar_continuo()
            self.btn_detener_trad.configure(state="normal")

    def detener_traduccion(self):
        if self.translator: self.translator.detener_continuo()
        self.btn_detener_trad.configure(state="disabled")
        self.log("⏹  Traducción detenida")


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print("\n========== ERROR AL INICIAR ==========")
        traceback.print_exc()
        print("======================================")
        input("\nPresiona ENTER para cerrar...")