import customtkinter as ctk
import threading, os, traceback, webbrowser, requests, time, json
try:
    import keyboard
    KEYBOARD_OK = True
except ImportError:
    KEYBOARD_OK = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_VERSION = "0.9.1-beta"
APP_NAME = "Karin VTuber -IA-"

from src.core.config import load_config
from src.audio import audio_worker, speak, stop_audio, get_output_devices
from src.ai import ask_ai
from src.bot.twitch_bot import start_chat
from src.core.oauth_server import TwitchOAuth, validate_token, fetch_twitch_game
from src.utils.ptt import PTTManager
from src.utils.game_watcher import GameWatcher

from src.utils import PIL_OK
from PIL import Image

config = load_config()

# Paleta moderna — dark mode con acentos purple/pink
BG     = "#0c0c18"; SIDE   = "#12121e"; CARD  = "#1a1a2e"; CARD2 = "#22223a"
BORD   = "#a855f7"; PURP   = "#c084fc"
GRN    = "#059669"; GRN_T  = "#a7f3d0"
RED    = "#dc2626"; RED_T  = "#fca5a5"
BLU    = "#2563eb"; BLU_T  = "#93c5fd"
AMB    = "#d97706"; AMB_T  = "#fcd34d"

TXT    = "#e2e8f0"; MUT    = "#94a3b8"; LOGBG = "#080812"

def mk(p, accent=False, **k):
    k.setdefault("fg_color", CARD); k.setdefault("corner_radius", 12)
    f = ctk.CTkFrame(p, **k)
    if accent:
        bar = ctk.CTkFrame(f, fg_color=BORD, height=3, corner_radius=0)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
    return f

def lb(p, t, sz=12, col=TXT, bold=False, **k):
    return ctk.CTkLabel(p, text=t, font=("Segoe UI", sz, "bold" if bold else "normal"),
                        text_color=col, **k)

def cb(p, vals, **k):
    k.setdefault("fg_color", CARD); k.setdefault("border_color", BORD)
    k.setdefault("button_color", PURP); k.setdefault("dropdown_fg_color", CARD2)
    k.setdefault("dropdown_hover_color", "#2a2a42")
    k.setdefault("font", ("Segoe UI", 11))
    return ctk.CTkComboBox(p, values=vals, **k)

def bt(p, t, bg, fg, cmd, h=36, **k):
    import colorsys
    def _lighten(hex_color, factor=0.15):
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
            l = min(1, l + factor * 0.3)
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        except:
            return bg
    return ctk.CTkButton(p, text=t, fg_color=bg, text_color=fg, hover_color=_lighten(bg),
                         font=("Segoe UI", 12, "bold"), corner_radius=10, height=h,
                         command=cmd, **k)


# ════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        print("App.__init__ started")
        super().__init__()
        print("super().__init__ done")
        self.title(f"{APP_NAME} v{APP_VERSION}")
        print("title set")
        self.geometry("1280x820")
        print("geometry set")
        
        # Nota: El icono de ventana requiere formato .ico, pero la app funciona sin él
        self.minsize(1100, 700)
        print("minsize set")
        self.configure(fg_color=BG)
        print("configure done")
        
        print("Starting audio worker thread...")
        threading.Thread(target=audio_worker, daemon=True).start()
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
        self._selected_prompt_file = selected_prompt_file
        self.current_prompt = ""
        
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
        mn_idx = int(config.get("MONITOR_DEVICE", 0))
        if mn_idx < len(self.dev_names):
            self._mn_default = self.dev_names[mn_idx]
        else:
            self._mn_default = "(Ninguno)"
        self.game_watcher = None
        self.lector_subtitulos = None
        self.hotkey_reader = None
        self._lectura_auto_activa = False
        
        # Todas las voces disponibles
        self.voices_all = ["es-ES-ElviraNeural", "es-ES-AlvaroNeural",
                           "es-MX-DaliaNeural", "es-MX-LiaNeural", "es-MX-DarioNeural",
                           "es-AR-EmiliaNeural", "es-AR-TonoNeural"]
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self._build_sidebar()
        self._build_content()
        
        # PTT
        saved_ptt_key = config.get("PTT_KEY", "F9")
        if PTTManager:
            try:
                saved_vol = float(config.get("VOLUME", "2.0"))
                self.ptt_obj = PTTManager(
                    app=self, ask_ai_fn=ask_ai, speak=speak,
                    stop_audio=stop_audio, config=config,
                    get_devices=self.get_devices,
                    current_prompt=lambda: self.current_prompt,
                    key=saved_ptt_key.lower(), voice="es-MX-DaliaNeural",
                    volume=saved_vol)
                self.log(f"⌨  PTT listo — mantén CTRL+{saved_ptt_key} para hablar")
            except Exception as e:
                self.log(f"⚠  PTT error: {e}")
        else:
            self.log("⚠  PTT no disponible — pip install keyboard")
        
        if not PIL_OK:
            self.log("Comentarista: pip install pillow")
        

    
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=SIDE, corner_radius=0, width=220)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        for r in range(11):
            sb.grid_rowconfigure(r, weight=1 if r == 3 else 0)
        
        hdr = ctk.CTkFrame(sb, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(16, 4))
        
        # Agregar logo
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "logo", "avatar.png")
            logo_img = ctk.CTkImage(light_image=Image.open(logo_path), size=(80, 80))
            ctk.CTkLabel(hdr, image=logo_img, text="").pack(anchor="center", pady=(0, 8))
        except Exception as e:
            print(f"Error cargando logo: {e}")
        
        lb(hdr, "Karin VTuber", sz=15, bold=True, col=PURP).pack(anchor="center")
        
        ctk.CTkFrame(sb, height=1, fg_color=BORD).grid(row=1, column=0, sticky="ew", padx=8)
        
        self._nav_btns = {}
        self._nav_indicators = {}
        self._nav_container = ctk.CTkFrame(sb, fg_color="transparent")
        self._nav_container.grid(row=3, column=0, sticky="nsew", padx=6, pady=4)
        sb.grid_rowconfigure(3, weight=1)

        buttons = [
            ("📊  Panel",        "panel"),
            ("🎧  Audio",        "audio"),
            ("🤖  Bot Speaker",  "bot_speaker"),
            ("💬  Chat Bot IA", "comentarista"),
            ("🔑  API Keys",     "api_key"),
            ("❓  Ayuda",        "creditos"),
        ]

        for i, (txt, key) in enumerate(buttons):
            row = ctk.CTkFrame(self._nav_container, fg_color="transparent", height=36)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            
            indicator = ctk.CTkFrame(row, fg_color="transparent", width=3, corner_radius=0)
            indicator.pack(side="left", fill="y")
            self._nav_indicators[key] = indicator
            
            b = ctk.CTkButton(row, text=txt, anchor="w", fg_color="transparent",
                              text_color=MUT, hover_color=CARD2, font=("Segoe UI", 12),
                              corner_radius=0, height=36, border_width=0,
                              command=lambda k=key: self._tab(k))
            b.pack(side="left", fill="x", expand=True, padx=(4, 0))
            self._nav_btns[key] = b
        
        ctk.CTkFrame(sb, height=1, fg_color="#2a2a3e").grid(row=9, column=0, sticky="ew", padx=12, pady=6)
        
        self.twitch_btn = ctk.CTkButton(
            sb, text="🔴  Twitch", fg_color="#9146FF", text_color="#fff",
            hover_color="#772CE8", font=("Segoe UI", 11, "bold"), corner_radius=10,
            height=34, command=self.connect_twitch)
        self.twitch_btn.grid(row=10, column=0, padx=8, pady=(4, 8), sticky="ew")
    
    def _tab(self, key):
        for k, b in self._nav_btns.items():
            is_active = (k == key)
            b.configure(fg_color=CARD2 if is_active else "transparent",
                        text_color=TXT if is_active else MUT)
            ind = self._nav_indicators.get(k)
            if ind:
                ind.configure(fg_color=BORD if is_active else "transparent")
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
        wrap.grid_rowconfigure(0, weight=0)
        wrap.grid_rowconfigure(1, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        
        # Topbar
        top = ctk.CTkFrame(wrap, fg_color=SIDE, corner_radius=0, height=48)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)
        
        # Accent bottom line
        ctk.CTkFrame(top, fg_color=BORD, height=2, corner_radius=0).grid(row=1, column=0, columnspan=3, sticky="ew")
        
        inner_top = ctk.CTkFrame(top, fg_color="transparent")
        inner_top.grid(row=0, column=0, sticky="ew", padx=14)
        inner_top.grid_columnconfigure(1, weight=1)
        lb(inner_top, "Panel de control", sz=14, bold=True).grid(row=0, column=0, sticky="w")
        lb(inner_top, f"v{APP_VERSION}", sz=10, col=MUT).grid(row=0, column=2, sticky="e", padx=(10, 0))
        

        
        # Área tabs
        area = ctk.CTkFrame(wrap, fg_color=BG, corner_radius=0)
        area.grid(row=1, column=0, sticky="nsew")
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)
        
        self._tabs = {
            "panel":        self._tab_panel(area),
            "audio":        self._tab_audio(area),
            "bot_speaker":  self._tab_bot_speaker(area),
            "comentarista": self._tab_comentarista(area),
            "api_key":      self._tab_api_key(area),
            "creditos":     self._tab_creditos(area),
        }
        self._tab("panel")
        self._nav_btns["panel"].configure(fg_color=CARD2, text_color=TXT)
        self._nav_indicators["panel"].configure(fg_color=BORD)
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB PANEL
    # ════════════════════════════════════════════════════════════════════════
    def _tab_panel(self, parent):
        tab = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=PURP, scrollbar_button_hover_color=BORD)
        
        # Log con acento
        lc = mk(tab, accent=True)
        lc.pack(fill="x", padx=14, pady=(12, 6))
        lb(lc, "📋  Actividad", sz=11, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        self.log_box = ctk.CTkTextbox(lc, height=150, font=("Consolas", 11),
                                      fg_color=LOGBG, text_color="#7dd3fc",
                                      border_width=0, corner_radius=6)
        self.log_box.pack(fill="x", padx=14, pady=(0, 12))
        
        # ── Push-to-Talk + Botones ──
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=4)
        row.grid_columnconfigure(0, weight=1)

        cv = mk(row, accent=True)
        cv.grid(row=0, column=0, sticky="ew")
        inner = ctk.CTkFrame(cv, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(10, 10))
        lb(inner, "🎤  Push-to-Talk", sz=11, bold=True, col=PURP).pack(side="left", padx=(0, 12))
        lb(inner, "CTRL +", sz=11, col=TXT).pack(side="left", padx=(0, 4))
        self.ptt_key_entry = ctk.CTkEntry(inner, width=60, font=("Consolas", 12, "bold"),
                                           fg_color=BG, text_color=TXT, border_color=BORD,
                                           justify="center")
        self.ptt_key_entry.pack(side="left", padx=(0, 12))
        saved_ptt_key = config.get("PTT_KEY", "F9")
        self.ptt_key_entry.insert(0, saved_ptt_key)
        lb(inner, "Mantén para hablar", sz=10, col=MUT).pack(side="left", padx=(0, 12))
        bt(inner, "🗑  Borrar memoria", RED, RED_T, self._borrar_memoria, h=32).pack(side="right", padx=(3, 0))
        bt(inner, "💾 Guardar config", GRN, GRN_T, self._guardar_config_panel, h=32).pack(side="right", padx=(3, 0))
        bt(inner, "🎤 Hablar", GRN, GRN_T, self.ptt_click, h=32).pack(side="right", padx=(3, 0))

        # ── Perfil de la IA ──
        pf = mk(tab, accent=True)
        pf.pack(fill="x", padx=14, pady=(6, 6))
        lb(pf, "🤖  Perfil de la IA", sz=11, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        lb(pf, "Prompt principal — los datos del perfil se anteponen a la personalidad", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))

        pf_grid = ctk.CTkFrame(pf, fg_color="transparent")
        pf_grid.pack(fill="x", padx=14)
        pf_grid.grid_columnconfigure(1, weight=1)
        pf_grid.grid_columnconfigure(3, weight=1)

        self._ia_nombre = ctk.StringVar(value=config.get("IA_NOMBRE", ""))
        lb(pf_grid, "Nombre:", sz=11, col=TXT, width=65).grid(row=0, column=0, padx=(0, 4), pady=3, sticky="w")
        ctk.CTkEntry(pf_grid, textvariable=self._ia_nombre, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=0, column=1, padx=(0, 12), pady=3, sticky="ew")
        lb(pf_grid, "Apellido:", sz=11, col=TXT, width=65).grid(row=0, column=2, padx=(0, 4), pady=3, sticky="w")
        self._ia_apellido = ctk.StringVar(value=config.get("IA_APELLIDO", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_apellido, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=0, column=3, padx=(0, 4), pady=3, sticky="ew")

        lb(pf_grid, "Edad:", sz=11, col=TXT, width=65).grid(row=1, column=0, padx=(0, 4), pady=3, sticky="w")
        self._ia_edad = ctk.StringVar(value=config.get("IA_EDAD", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_edad, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=1, column=1, padx=(0, 12), pady=3, sticky="ew")
        lb(pf_grid, "Género:", sz=11, col=TXT, width=65).grid(row=1, column=2, padx=(0, 4), pady=3, sticky="w")
        self._ia_genero = ctk.StringVar(value=config.get("IA_GENERO", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_genero, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=1, column=3, padx=(0, 4), pady=3, sticky="ew")

        lb(pf_grid, "Cumpleaños:", sz=11, col=TXT, width=80).grid(row=2, column=0, padx=(0, 4), pady=3, sticky="w")
        self._ia_cumple = ctk.StringVar(value=config.get("IA_CUMPLE", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_cumple, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=2, column=1, padx=(0, 12), pady=3, sticky="ew")
        lb(pf_grid, "Signo Zodiacal:", sz=11, col=TXT, width=100).grid(row=2, column=2, padx=(0, 4), pady=3, sticky="w")
        self._ia_signo = ctk.StringVar(value=config.get("IA_SIGNO", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_signo, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=2, column=3, padx=(0, 4), pady=3, sticky="ew")

        lb(pf_grid, "Altura:", sz=11, col=TXT, width=65).grid(row=3, column=0, padx=(0, 4), pady=3, sticky="w")
        self._ia_altura = ctk.StringVar(value=config.get("IA_ALTURA", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_altura, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=3, column=1, padx=(0, 12), pady=3, sticky="ew")
        lb(pf_grid, "Trabajo:", sz=11, col=TXT, width=65).grid(row=3, column=2, padx=(0, 4), pady=3, sticky="w")
        self._ia_trabajo = ctk.StringVar(value=config.get("IA_TRABAJO", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_trabajo, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=3, column=3, padx=(0, 4), pady=3, sticky="ew")

        lb(pf_grid, "Gustos:", sz=11, col=TXT, width=65).grid(row=4, column=0, padx=(0, 4), pady=3, sticky="w")
        self._ia_gustos = ctk.StringVar(value=config.get("IA_GUSTOS", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_gustos, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=4, column=1, columnspan=3, padx=(0, 4), pady=3, sticky="ew")

        lb(pf_grid, "Frases típicas:", sz=11, col=TXT, width=65).grid(row=5, column=0, padx=(0, 4), pady=3, sticky="w")
        self._ia_frases = ctk.StringVar(value=config.get("IA_FRASES", ""))
        ctk.CTkEntry(pf_grid, textvariable=self._ia_frases, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=5, column=1, columnspan=3, padx=(0, 4), pady=3, sticky="ew")

        # ── Personalidad ──
        sep = ctk.CTkFrame(pf, height=1, fg_color="#2a2a3e")
        sep.pack(fill="x", padx=14, pady=(10, 6))
        lb_row = ctk.CTkFrame(pf, fg_color="transparent")
        lb_row.pack(fill="x", padx=14)
        lb(lb_row, "🧠  Personalidad", sz=11, bold=True, col=PURP).pack(side="left")
        lb(lb_row, "Prompt activo", sz=10, col=MUT).pack(side="left", padx=(12, 0))
        self.mode_select = cb(pf, self.prompt_files, command=self.change_mode)
        self.mode_select.pack(fill="x", padx=14, pady=(4, 0))
        initial_prompt = config.get("SELECTED_PROMPT", self.prompt_files[0])
        if initial_prompt not in self.prompt_files:
            initial_prompt = self.prompt_files[0]
        self.mode_select.set(initial_prompt)

        btn_row = ctk.CTkFrame(pf, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(6, 10))
        ctk.CTkButton(btn_row, text="+ Nueva Personalidad",
                      fg_color=CARD2, text_color=TXT,
                      hover_color=PURP, height=28, corner_radius=8,
                      command=self._crear_nuevo_prompt).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="💾 Guardar Perfil",
                      fg_color=GRN, text_color=GRN_T,
                      height=28, corner_radius=8,
                      command=self._guardar_config_panel).pack(side="left")

        # ── Perfil del Streamer / Player ──
        pf2 = mk(tab, accent=True)
        pf2.pack(fill="x", padx=14, pady=(6, 6))
        lb(pf2, "🎮  Perfil del Streamer / Player", sz=11, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        lb(pf2, "Datos del compañero — la IA usará esta información para interactuar contigo", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))

        pg = ctk.CTkFrame(pf2, fg_color="transparent")
        pg.pack(fill="x", padx=14, pady=(0, 10))
        pg.grid_columnconfigure(1, weight=1)
        pg.grid_columnconfigure(3, weight=1)

        field_defs = [
            ("Nombre:", 0, 0, "_player_nombre", "PLAYER_NOMBRE"),
            ("Apellido:", 0, 2, "_player_apellido", "PLAYER_APELLIDO"),
            ("Edad:", 1, 0, "_player_edad", "PLAYER_EDAD"),
            ("Género:", 1, 2, "_player_genero", "PLAYER_GENERO"),
            ("Cumpleaños:", 2, 0, "_player_cumple", "PLAYER_CUMPLE"),
            ("Signo Zodiacal:", 2, 2, "_player_signo", "PLAYER_SIGNO"),
            ("Altura:", 3, 0, "_player_altura", "PLAYER_ALTURA"),
            ("Trabajo:", 3, 2, "_player_trabajo", "PLAYER_TRABAJO"),
            ("Relación:", 6, 0, "_player_relacion", "PLAYER_RELACION"),
        ]
        for label, row, col, attr, cfg_key in field_defs:
            lb(pg, label, sz=11, col=TXT, width=65 if col == 0 else 80).grid(row=row, column=col, padx=(0, 4), pady=3, sticky="w")
            setattr(self, attr, ctk.StringVar(value=config.get(cfg_key, "")))
            if cfg_key == "PLAYER_RELACION":
                opciones = ["", "SIMP", "Compañeros", "Amig@", "Novi@", "Amante",
                            "Espos@", "Waifu", "Sirvienta/Mayordomo", "Esclava/o Sexual", "Fan tóxico"]
                c = cb(pg, opciones, variable=getattr(self, attr), width=180)
                c.grid(row=row, column=col + 1, columnspan=3, padx=(0, 4), pady=3, sticky="w")
            else:
                ctk.CTkEntry(pg, textvariable=getattr(self, attr), font=("Consolas", 11),
                             fg_color=CARD, text_color=TXT, border_color=BORD).grid(
                    row=row, column=col + 1, padx=(0, 12) if col == 0 else (0, 4), pady=3, sticky="ew")

        lb(pg, "Gustos:", sz=11, col=TXT, width=65).grid(row=4, column=0, padx=(0, 4), pady=3, sticky="w")
        self._player_gustos = ctk.StringVar(value=config.get("PLAYER_GUSTOS", ""))
        ctk.CTkEntry(pg, textvariable=self._player_gustos, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=4, column=1, columnspan=3, padx=(0, 4), pady=3, sticky="ew")

        lb(pg, "Frases típicas:", sz=11, col=TXT, width=65).grid(row=5, column=0, padx=(0, 4), pady=3, sticky="w")
        self._player_frases = ctk.StringVar(value=config.get("PLAYER_FRASES", ""))
        ctk.CTkEntry(pg, textvariable=self._player_frases, font=("Consolas", 11),
                     fg_color=CARD, text_color=TXT, border_color=BORD).grid(row=5, column=1, columnspan=3, padx=(0, 4), pady=3, sticky="ew")

        btn_row2 = ctk.CTkFrame(pf2, fg_color="transparent")
        btn_row2.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkButton(btn_row2, text="💾 Guardar Perfil del Streamer",
                      fg_color=GRN, text_color=GRN_T,
                      height=28, corner_radius=8,
                      command=self._guardar_config_panel).pack(side="left")

        self._build_prompt(self._selected_prompt_file)

        return tab
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB AUDIO
    # ════════════════════════════════════════════════════════════════════════
    def _tab_audio(self, parent):
        tab = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=PURP, scrollbar_button_hover_color=BORD)
        
        c = mk(tab, accent=True)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🔊  Dispositivos de audio", sz=12, bold=True).pack(anchor="w", padx=14, pady=(10, 4))
        for txt, attr, default in [
            ("Bot Speaker", "sp2", self._sp_default),
            ("IA Voz", "ia2", self._ia_default),
            ("Monitor", "mn2", self._mn_default),
        ]:
            lb(c, txt, sz=10, col=MUT).pack(anchor="w", padx=14, pady=(4, 0))
            vals = (["(Ninguno)"] + self.dev_names) if "Monitor" in txt else self.dev_names
            bx = cb(c, vals); bx.pack(fill="x", padx=14, pady=(0, 4))
            if default in vals:
                bx.set(default)
            else:
                bx.set(vals[0])
            setattr(self, attr, bx)
        ctk.CTkFrame(c, height=6, fg_color="transparent").pack()
        
        ctk.CTkButton(c, text="💾 Guardar dispositivos", fg_color=GRN, text_color=GRN_T,
                      height=30, corner_radius=8, hover_color="#10b981",
                      command=self._guardar_audio_devices).pack(padx=14, pady=(0, 10))
        
        return tab
    
    def _guardar_audio_devices(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        if hasattr(self, 'sp2'):
            idx = self.sp2.get()
            cfg["SPEAKER_DEVICE"] = str(self.dev_names.index(idx)) if idx in self.dev_names else "0"
        if hasattr(self, 'ia2'):
            idx = self.ia2.get()
            cfg["IA_DEVICE"] = str(self.dev_names.index(idx) if idx in self.dev_names else 0)
        if hasattr(self, 'mn2'):
            idx = self.mn2.get()
            if idx in ("(Ninguno)", ""):
                cfg.pop("MONITOR_DEVICE", None)
            else:
                cfg["MONITOR_DEVICE"] = str(self.dev_names.index(idx) if idx in self.dev_names else 0)
        save_config(cfg)
        self.log(f"✅  Dispositivos guardados: Speaker={cfg.get('SPEAKER_DEVICE','?')}, IA={cfg.get('IA_DEVICE','?')}, Monitor={cfg.get('MONITOR_DEVICE','ninguno')}")
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB BOT SPEAKER
    # ════════════════════════════════════════════════════════════════════════
    def _tab_bot_speaker(self, parent):
        tab = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=PURP, scrollbar_button_hover_color=BORD)
        
        c = mk(tab, accent=True)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🔧  Bot Speaker", sz=12, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(c, "Comandos para reproducir audio en Twitch", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))
        
        self.voices_male = ["es-ES-AlvaroNeural", "es-MX-DarioNeural", "es-AR-TonoNeural"]
        self.voices_female = ["es-ES-ElviraNeural", "es-MX-LiaNeural", "es-MX-DaliaNeural", "es-AR-EmiliaNeural"]
        
        saved_male = config.get("BOT_VOICE_MALE", "es_MX-DarioNeural")
        saved_female = config.get("BOT_VOICE_FEMALE", "es-MX-DaliaNeural")
        
        cmd_frame = mk(c)
        cmd_frame.pack(fill="x", padx=14, pady=(0, 10))
        
        # Fila: Comando Speak masculino
        row1 = ctk.CTkFrame(cmd_frame, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(10, 4))
        row1.grid_columnconfigure(1, weight=1)
        lb(row1, "!sp comando:", sz=10, col=MUT, width=95).grid(row=0, column=0, sticky="w")
        self.cmd_speak_entry = ctk.CTkEntry(row1, placeholder_text="!sp",
                                        font=("Consolas", 12),
                                        fg_color=CARD, text_color=TXT, border_color=BORD)
        self.cmd_speak_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.cmd_speak_entry.insert(0, config.get("BOT_SPEAK_CMD", "!sp"))
        
        lb(row1, "Voz:", sz=10, col=MUT, width=30).grid(row=0, column=2, padx=(8, 4))
        self.voice_male_var = ctk.StringVar(value=saved_male)
        self.voice_male_menu = ctk.CTkOptionMenu(row1, values=self.voices_male,
                                              variable=self.voice_male_var,
                                              fg_color=CARD, button_color=PURP, dropdown_fg_color=CARD2,
                                              text_color=TXT, font=("Segoe UI", 11), width=140)
        self.voice_male_menu.grid(row=0, column=3, padx=(0, 0))
        
        # Separador
        ctk.CTkFrame(cmd_frame, height=1, fg_color="#2a2a3e").pack(fill="x", padx=14, pady=4)
        
        # Fila: Comando SpeakMap femenino
        row2 = ctk.CTkFrame(cmd_frame, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=(4, 10))
        row2.grid_columnconfigure(1, weight=1)
        lb(row2, "!spm comando:", sz=10, col=MUT, width=95).grid(row=0, column=0, sticky="w")
        self.cmd_speakmap_entry = ctk.CTkEntry(row2, placeholder_text="!spm",
                                              font=("Consolas", 12),
                                              fg_color=CARD, text_color=TXT, border_color=BORD)
        self.cmd_speakmap_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.cmd_speakmap_entry.insert(0, config.get("BOT_SPEAKMAP_CMD", "!spm"))
        
        lb(row2, "Voz:", sz=10, col=MUT, width=30).grid(row=0, column=2, padx=(8, 4))
        self.voice_female_var = ctk.StringVar(value=saved_female)
        self.voice_female_menu = ctk.CTkOptionMenu(row2, values=self.voices_female,
                                                    variable=self.voice_female_var,
                                                    fg_color=CARD, button_color=PURP, dropdown_fg_color=CARD2,
                                                    text_color=TXT, font=("Segoe UI", 11), width=140)
        self.voice_female_menu.grid(row=0, column=3)
        
        # Botones
        btn_frame = ctk.CTkFrame(c, fg_color="transparent")
        btn_frame.pack(fill="x", padx=14, pady=(0, 10))
        btn_frame.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_frame, text="💾 Guardar comandos", fg_color=GRN, text_color=GRN_T,
                     height=34, corner_radius=8, hover_color="#10b981",
                     command=self._guardar_bot_cmds).grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkButton(btn_frame, text="🧪 Test", fg_color=PURP, text_color="#f3e8ff",
                     height=34, corner_radius=8, hover_color="#a855f7",
                     command=self._test_bot_speaker).grid(row=0, column=1, padx=(4, 0), sticky="ew")
        
        # ── Sonidos personalizados ──
        audio_card = mk(tab, accent=True)
        audio_card.pack(fill="x", padx=14, pady=(8, 6))
        lb(audio_card, "🔊  Sonidos personalizados", sz=12, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(audio_card, "Sube archivos MP3 y asígnales un comando para Twitch", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))
        
        self._audio_slots = []
        audio_inner = ctk.CTkFrame(audio_card, fg_color="transparent")
        audio_inner.pack(fill="x", padx=14, pady=(0, 10))
        
        for i in range(1, 6):
            row = ctk.CTkFrame(audio_inner, fg_color="transparent")
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(1, weight=1)
            
            lb(row, f"#{i}", sz=11, col=PURP, width=22).grid(row=0, column=0, padx=(0, 4))
            
            path_var = ctk.StringVar(value=config.get(f"AUDIO_FILE_{i}", ""))
            entry_path = ctk.CTkEntry(row, textvariable=path_var,
                                       font=("Consolas", 10), fg_color=CARD, text_color=MUT,
                                       border_color="#2a2a3e", state="readonly")
            entry_path.grid(row=0, column=1, sticky="ew", padx=(0, 4))
            
            cmd_var = ctk.StringVar(value=config.get(f"AUDIO_CMD_{i}", ""))
            entry_cmd = ctk.CTkEntry(row, textvariable=cmd_var, placeholder_text="!comando",
                                      font=("Consolas", 11, "bold"), width=120,
                                      fg_color=CARD, text_color=TXT, border_color=BORD)
            entry_cmd.grid(row=0, column=2, padx=(0, 4))
            
            ctk.CTkButton(row, text="📂", fg_color=CARD2, text_color=TXT, width=32, height=28,
                          corner_radius=6, command=lambda idx=i, pv=path_var: self._seleccionar_audio(idx, pv)).grid(row=0, column=3, padx=(0, 2))
            ctk.CTkButton(row, text="▶", fg_color=CARD2, text_color=GRN_T, width=32, height=28,
                          corner_radius=6, command=lambda pv=path_var: self._reprobar_audio(pv.get())).grid(row=0, column=4)
            
            self._audio_slots.append((i, path_var, cmd_var))
        
        ctk.CTkButton(audio_card, text="💾 Guardar sonidos", fg_color=GRN, text_color=GRN_T,
                      height=30, corner_radius=8, hover_color="#10b981",
                      command=self._guardar_audio_slots).pack(padx=14, pady=(0, 10))
        
        return tab
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB CHAT BOT IA
    # ════════════════════════════════════════════════════════════════════════
    def _tab_comentarista(self, parent):
        tab = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=PURP, scrollbar_button_hover_color=BORD)
        
        # ── IA Chat para Twitch ──
        ia_card = mk(tab, accent=True)
        ia_card.pack(fill="x", padx=14, pady=(12, 6))
        lb(ia_card, "🤖  IA para Chat de Twitch", sz=13, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(ia_card, "Los viewers escriben el comando en el chat y la IA responde con voz", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))
        
        ia_grid = ctk.CTkFrame(ia_card, fg_color="transparent")
        ia_grid.pack(fill="x", padx=14, pady=(4, 10))
        ia_grid.grid_columnconfigure(1, weight=1)
        
        lb(ia_grid, "Comando:", sz=11, col=MUT).grid(row=0, column=0, sticky="w")
        self.ia_cmd_entry = ctk.CTkEntry(ia_grid, placeholder_text="!IA",
                                           font=("Consolas", 12, "bold"),
                                           fg_color=CARD, text_color=TXT, border_color=BORD, width=100)
        self.ia_cmd_entry.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)
        ia_cmd_val = config.get("BOT_IA_COMMAND", "!IA")
        self.ia_cmd_entry.insert(0, ia_cmd_val)
        
        lb(ia_grid, "IA para Comentarista:", sz=11, col=MUT).grid(row=1, column=0, sticky="w")
        self.comentador_ia_provider = ctk.CTkComboBox(ia_grid, values=["Groq", "Cerebras", "Google Studio IA"],
                                                       fg_color=CARD, button_color=PURP,
                                                       dropdown_fg_color=CARD2, text_color=TXT,
                                                       border_color=BORD, font=("Segoe UI", 11))
        self.comentador_ia_provider.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        ia_provider_val = config.get("COMENTADOR_IA_PROVIDER", "Groq")
        self.comentador_ia_provider.set(ia_provider_val)
        
        lb(ia_grid, "Voz TTS:", sz=11, col=MUT).grid(row=2, column=0, sticky="w", pady=(6, 0))
        voz_row = ctk.CTkFrame(ia_grid, fg_color="transparent")
        voz_row.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        voz_row.grid_columnconfigure(0, weight=1)
        self.ia_voice_menu = ctk.CTkComboBox(voz_row, values=self.voices_all,
                                               fg_color=CARD, button_color=PURP,
                                               dropdown_fg_color=CARD2, text_color=TXT,
                                               border_color=BORD, font=("Segoe UI", 11))
        self.ia_voice_menu.grid(row=0, column=0, sticky="ew")
        self.ia_voice_menu.set(config.get("BOT_IA_VOICE", "es-MX-DaliaNeural"))
        ctk.CTkButton(voz_row, text="🔊 Test", fg_color=CARD2, text_color=TXT,
                      hover_color=PURP, height=28, corner_radius=6,
                      command=self._test_ia_voice).grid(row=0, column=1, padx=(6, 0))
        
        ctk.CTkButton(ia_grid, text="💾 Guardar comando IA", fg_color=GRN, text_color=GRN_T,
                      height=30, corner_radius=8, hover_color="#10b981",
                      command=self._guardar_ia_command).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=(10, 0))
        
        # ── Comentarista ──
        c = mk(tab, accent=True)
        c.pack(fill="x", padx=14, pady=(8, 6))
        lb(c, "🎮  Asistente IA", sz=13, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        
        opts = mk(c)
        opts.pack(fill="x", padx=14, pady=(0, 10))
        
        grid = ctk.CTkFrame(opts, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(10, 4))
        grid.grid_columnconfigure(1, weight=1)
        
        # ── Juego ──
        lb(grid, "🎮 Juego:", sz=11, col=MUT).grid(row=0, column=0, sticky="w", pady=3)
        game_row = ctk.CTkFrame(grid, fg_color="transparent")
        game_row.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
        game_row.grid_columnconfigure(0, weight=1)
        juego_inicial = config.get("COMENTARISTA_JUEGO", "")
        self.juego_entry = ctk.CTkEntry(game_row, placeholder_text="ej: Minecraft",
                                         font=("Segoe UI", 12, "bold"),
                                         fg_color=CARD, text_color=TXT, border_color=BORD)
        self.juego_entry.grid(row=0, column=0, sticky="ew")
        if juego_inicial:
            self.juego_entry.insert(0, juego_inicial)
        detect_btn = ctk.CTkButton(game_row, text="🎮", fg_color=CARD2, text_color=TXT,
                                   hover_color=PURP, width=32, height=28, corner_radius=6,
                                   command=self._detectar_juego_twitch)
        detect_btn.grid(row=0, column=1, padx=(6, 0))
        
        # ── Intervalo ──
        lb(grid, "⏱ Intervalo (seg):", sz=11, col=MUT).grid(row=1, column=0, sticky="w", pady=3)
        irow = ctk.CTkFrame(grid, fg_color="transparent")
        irow.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.comentarista_intervalo = ctk.CTkEntry(irow, placeholder_text="30",
                                                     fg_color=CARD, text_color=TXT, border_color=BORD,
                                                     font=("Segoe UI", 11), width=80)
        self.comentarista_intervalo.pack(side="left")
        self.comentarista_intervalo.insert(0, str(config.get("COMENTARISTA_INTERVALO", 30)))
        
        # ── Cooldown ──
        lb(grid, "🔥 Cooldown (seg):", sz=11, col=MUT).grid(row=2, column=0, sticky="w", pady=3)
        cdown_row = ctk.CTkFrame(grid, fg_color="transparent")
        cdown_row.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.comentarista_cooldown = ctk.CTkEntry(cdown_row, placeholder_text="30",
                                                   fg_color=CARD, text_color=TXT, border_color=BORD,
                                                   font=("Segoe UI", 11), width=80)
        self.comentarista_cooldown.pack(side="left")
        self.comentarista_cooldown.insert(0, str(config.get("COMENTARISTA_COOLDOWN", 30)))
        
        # ── Switches de módulos ──
        sw_card = mk(c)
        sw_card.pack(fill="x", padx=14, pady=(0, 6))
        lb(sw_card, "🔧  Módulos activos", sz=11, bold=True, col=PURP).pack(anchor="w", padx=12, pady=(8, 4))
        
        def _crear_switch(parent, texto, attr_switch, attr_indicador, default=True, badge=None):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            row.grid_columnconfigure(1, weight=1)
            var = ctk.BooleanVar(value=config.get(attr_switch.upper(), "1") == "1")
            sw = ctk.CTkSwitch(row, text=texto, variable=var, onvalue=True, offvalue=False,
                               fg_color=CARD2, progress_color=BORD, button_color=PURP,
                               font=("Segoe UI", 11))
            sw.grid(row=0, column=0, sticky="w")
            if badge:
                lb(row, badge, sz=8, col="#f59e0b").grid(row=0, column=1, sticky="w", padx=(4, 0))
            ind = lb(row, "●", sz=14, col=GRN_T if var.get() else RED_T)
            ind.grid(row=0, column=2, sticky="e", padx=(0, 4))
            def _on_toggle(*_a):
                try:
                    ind.configure(text_color=GRN_T if var.get() else RED_T)
                    from src.core.config import load_config, save_config
                    cfg = load_config()
                    cfg[attr_switch.upper()] = "1" if var.get() else "0"
                    config[attr_switch.upper()] = cfg[attr_switch.upper()]
                    save_config(cfg)
                    self._reiniciar_comentarista()
                except Exception as ex:
                    self.log(f"⚠ Error al cambiar {attr_switch}: {ex}")
                    import traceback
                    self.log(traceback.format_exc())
            var.trace_add("write", _on_toggle)
            setattr(self, attr_switch, var)
            setattr(self, attr_indicador, ind)
        
        sw_inner = ctk.CTkFrame(sw_card, fg_color="transparent")
        sw_inner.pack(fill="x", padx=0, pady=(0, 6))
        sw_inner.grid_columnconfigure((0, 1), weight=1)
        
        col1 = ctk.CTkFrame(sw_inner, fg_color="transparent")
        col1.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        col2 = ctk.CTkFrame(sw_inner, fg_color="transparent")
        col2.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        
        _crear_switch(col1, "📖 OCR", "sw_ocr", "ind_ocr")
        _crear_switch(col1, "👁️ Karin Vision", "sw_karin_vision", "ind_karin_vision", badge="⚗ Experimental")
        _crear_switch(col2, "🎭 Karin Animadora", "sw_karin_animadora", "ind_karin_animadora")
        _crear_switch(col2, "🟢 Groq Vision", "sw_groq_vision", "ind_groq_vision")
        _crear_switch(col2, "🔵 Google Vision", "sw_google_vision", "ind_google_vision")
        
        btns = ctk.CTkFrame(c, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=(0, 10))
        btns.grid_columnconfigure((0, 1, 2), weight=1)
        
        self.comentarista_btn = ctk.CTkButton(btns, text="▶ Iniciar", fg_color=GRN, text_color=GRN_T,
            font=("Segoe UI", 12, "bold"), corner_radius=10, height=36,
            command=self._iniciar_comentarista)
        self.comentarista_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        
        ctk.CTkButton(btns, text="⏹ Detener", fg_color=RED, text_color=RED_T,
            font=("Segoe UI", 12, "bold"), corner_radius=10, height=36,
            command=self._detener_comentarista).grid(row=0, column=1, padx=(4, 4), sticky="ew")
        
        ctk.CTkButton(btns, text="💾 Guardar", fg_color=BLU, text_color=BLU_T,
            font=("Segoe UI", 11), corner_radius=10, height=36,
            command=self._guardar_config_comentarista).grid(row=0, column=2, padx=(4, 0), sticky="ew")
        
        c_log_frame = mk(tab)
        c_log_frame.pack(fill="both", expand=True, padx=14, pady=(8, 12))
        lb(c_log_frame, "📋  Log del Comentarista", sz=10, bold=True, col=MUT).pack(anchor="w", padx=10, pady=(6, 2))
        self.comentarista_log = ctk.CTkTextbox(c_log_frame, fg_color=LOGBG, text_color=TXT,
                                                font=("Consolas", 10), height=200)
        self.comentarista_log.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        
        return tab
    
    def _detectar_juego_twitch(self):
        """Obtiene el juego actual desde la API de Twitch"""
        tok = config.get("TWITCH_TOKEN", "")
        chan = config.get("CHANNEL", "")
        if not tok or not chan:
            self._log_comentarista("⚠  No hay sesión de Twitch activa")
            return
        self._log_comentarista("🔍  Detectando juego desde Twitch...")
        import threading
        threading.Thread(target=self._fetch_game_thread, args=(tok, chan), daemon=True).start()
    
    def _fetch_game_thread(self, tok, chan):
        juego = fetch_twitch_game(tok, chan)
        if juego:
            self.juego_entry.delete(0, "end")
            self.juego_entry.insert(0, juego)
            config["COMENTARISTA_JUEGO"] = juego
            self._log_comentarista(f"✅  Juego detectado: {juego}")
        else:
            self._log_comentarista("❌  No se pudo detectar el juego")
    
    def _test_api(self, provider, key):
        if not key:
            self.log(f"❌  Ingresa una API Key primero")
            return
        if provider == "cerebras":
            import requests, json
            try:
                r = requests.post("https://api.cerebras.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": "llama3.1-8b", "messages": [{"role": "user", "content": "test"}], "max_tokens": 5},
                    timeout=15)
                self.log(f"✅  Cerebras API responde: {r.status_code}")
            except Exception as e:
                self.log(f"❌  Cerebras error: {e}")
        elif provider == "groq":
            import requests
            try:
                r = requests.get("https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}, timeout=10)
                self.log(f"✅  Groq API responde: {r.status_code}")
            except Exception as e:
                self.log(f"❌  Groq error: {e}")
        elif provider == "google_studio":
            import requests
            try:
                url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + key
                r = requests.post(url, 
                    json={"contents": [{"parts": [{"text": "test"}]}]},
                    timeout=15)
                self.log(f"✅  Google Studio IA API responde: {r.status_code}")
            except Exception as e:
                self.log(f"❌  Google Studio IA error: {e}")
    
    def _iniciar_comentarista(self):
        # Construir modo desde switches
        # ── Construir modo desde switches ──
        partes = []
        if hasattr(self, 'sw_ocr') and self.sw_ocr.get():
            partes.append("OCR")
        if hasattr(self, 'sw_karin_vision') and self.sw_karin_vision.get():
            partes.append("Karin Vision")
        if hasattr(self, 'sw_groq_vision') and self.sw_groq_vision.get():
            partes.append("Groq Vision")
        if hasattr(self, 'sw_google_vision') and self.sw_google_vision.get():
            partes.append("Google Vision")
        if hasattr(self, 'sw_karin_animadora') and self.sw_karin_animadora.get():
            partes.append("Karin Animadora")
        modo = " + ".join(partes) if partes else "OCR"
        juego = self.juego_entry.get().strip()
        voz = self.ia_voice_menu.get()
        try:
            cooldown = int(self.comentarista_cooldown.get().strip() or 30)
        except ValueError:
            cooldown = 30
            self.log("⚠  Cooldown inválido, usando 30 seg")
        
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["COMENTARISTA_JUEGO"] = juego
        cfg["COMENTARISTA_VOICE"] = voz
        cfg["COMENTARISTA_MODO"] = modo
        cfg["COMENTARISTA_COOLDOWN"] = cooldown
        save_config(cfg)
        for k, v in cfg.items():
            config[k] = v
        
        # Obtener API Key según el modo real, no el dropdown
        ia_key, ia_provider = self._obtener_key_por_modo(modo, cfg)
        if not ia_key:
            self.log(f"❌  Se necesita API Key para el modo {modo}")
            return
        self.log(f" IA disponible ({ia_provider})")
        
        if self.game_watcher:
            self.game_watcher.detener()
        
        self.game_watcher = GameWatcher(
            speak_fn=speak,
            stop_audio_fn=stop_audio,
            get_devices_fn=lambda: self.get_devices(),
            log_fn=self._log_comentarista
        )
        self.game_watcher.iniciar(voz=voz, juego=juego, modo=modo, ia_key=ia_key, ia_provider=ia_provider, cooldown=cooldown)
        self.log(f" Comentarista iniciado ({modo})")

    def _reiniciar_comentarista(self):
        if self.game_watcher is None:
            return
        try:
            partes = []
            if hasattr(self, 'sw_ocr') and self.sw_ocr.get():
                partes.append("OCR")
            if hasattr(self, 'sw_karin_vision') and self.sw_karin_vision.get():
                partes.append("Karin Vision")
            if hasattr(self, 'sw_groq_vision') and self.sw_groq_vision.get():
                partes.append("Groq Vision")
            if hasattr(self, 'sw_google_vision') and self.sw_google_vision.get():
                partes.append("Google Vision")
            if hasattr(self, 'sw_karin_animadora') and self.sw_karin_animadora.get():
                partes.append("Karin Animadora")
            modo = " + ".join(partes) if partes else "OCR"
            self.log(f"🔄  Reiniciando comentarista: {modo}")
            old = self.game_watcher
            old.detener()
            juego = self.juego_entry.get().strip()
            voz = self.ia_voice_menu.get()
            try:
                cooldown = int(self.comentarista_cooldown.get().strip() or 30)
            except ValueError:
                cooldown = 30
            from src.core.config import load_config
            cfg = load_config()
            ia_key, ia_provider = self._obtener_key_por_modo(modo, cfg)
            if not ia_key:
                self.log("❌  No hay API Key para reiniciar")
                self.game_watcher = None
                return
            self.game_watcher = GameWatcher(
                speak_fn=speak,
                stop_audio_fn=stop_audio,
                get_devices_fn=lambda: self.get_devices(),
                log_fn=self._log_comentarista
            )
            self.game_watcher.iniciar(voz=voz, juego=juego, modo=modo, ia_key=ia_key, ia_provider=ia_provider, cooldown=cooldown)
        except Exception as ex:
            self.log(f"⚠ Error al reiniciar comentarista: {ex}")
            import traceback
            self.log(traceback.format_exc())
            self.game_watcher = None
    
    def _obtener_key_por_modo(self, modo, cfg):
        """Retorna (ia_key, ia_provider) según el modo real, no el dropdown."""
        if "Google Vision" in modo:
            key = cfg.get("GOOGLE_STUDIO_API_KEY", "")
            return key, "google_studio"
        if "Groq Vision" in modo:
            key = cfg.get("GROQ_API_KEY", "")
            return key, "groq"
        ia_provider = self.comentador_ia_provider.get().lower().replace(" ", "_")
        mapa = {"google_studio_ia": "google_studio", "groq": "groq", "cerebras": "cerebras"}
        ia_provider = mapa.get(ia_provider, "groq")
        cfg_key = {"google_studio": "GOOGLE_STUDIO_API_KEY", "cerebras": "CEREBRAS_API_KEY"}.get(ia_provider, "GROQ_API_KEY")
        key = cfg.get(cfg_key, "")
        return key, ia_provider

    def _detener_comentarista(self):
        if self.game_watcher:
            self.game_watcher.detener()
            self.game_watcher = None
        self.log("⏹ Comentarista detenido")
    
    def _guardar_config_comentarista(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["COMENTARISTA_JUEGO"] = self.juego_entry.get().strip()
        cfg["COMENTARISTA_INTERVALO"] = int(self.comentarista_intervalo.get().strip() or 30)
        cfg["COMENTARISTA_MODO"] = "OCR"
        cfg["COMENTADOR_IA_PROVIDER"] = self.comentador_ia_provider.get()
        for key, attr in [("SW_OCR", "sw_ocr"), ("SW_KARIN_VISION", "sw_karin_vision"),
                          ("SW_KARIN_ANIMADORA", "sw_karin_animadora"), ("SW_VISION_IA", "sw_vision_ia")]:
            if hasattr(self, attr):
                cfg[key] = "1" if getattr(self, attr).get() else "0"
        cfg.pop("SUBTITULOS_INTERVALO", None)
        cfg.pop("PLAYER_MODO", None)
        cfg.pop("PLAYER_INPUT", None)
        cfg.pop("PLAYER_JUEGO", None)
        save_config(cfg)
        for k, v in cfg.items():
            config[k] = v
        self.log("✅ Configuración del comentarista guardada")

    def _guardar_ia_command(self):
        cmd = self.ia_cmd_entry.get().strip()
        voz = self.ia_voice_menu.get()
        provider = self.comentador_ia_provider.get()
        if not cmd:
            self.log("❌  Ingresa un comando válido")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["BOT_IA_COMMAND"] = cmd
        cfg["BOT_IA_VOICE"] = voz
        cfg["COMENTADOR_IA_PROVIDER"] = provider
        save_config(cfg)
        config["BOT_IA_COMMAND"] = cmd
        config["BOT_IA_VOICE"] = voz
        config["COMENTADOR_IA_PROVIDER"] = provider
        self.log(f"✅  Comando IA guardado: {cmd} → voz: {voz} | Proveedor: {provider}")

    def _test_ia_voice(self):
        voz = self.ia_voice_menu.get()
        from src.core.config import load_config
        cfg = load_config()
        ia_dev = int(cfg.get("IA_DEVICE", 2))
        from src.audio import speak
        vol = float(config.get("VOLUME", "2.0"))
        speak("Hola, soy tu asistente de voz. Esta es una prueba.", voz, ia_dev, volume=vol)

    def _log_comentarista(self, msg):
        self.comentarista_log.insert("end", f"{msg}\n")
        self.comentarista_log.see("end")
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB API_KEY
    # ════════════════════════════════════════════════════════════════════════
    def _tab_api_key(self, parent):
        tab = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=PURP, scrollbar_button_hover_color=BORD)
        
        c = mk(tab, accent=True)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🔑  API Keys", sz=13, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(c, "Configura las claves de los proveedores de IA", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))
        
        for provider, icon, title, usage, entry_attr, placeholder_key, cfg_key, link_url, test_fn, guardar_fn in [
            ("cerebras", "🟡", "Cerebras", "Chat Bot, PTT, Twitch",
             "cere_key_entry", "csk_...", "CEREBRAS_API_KEY",
             "https://cloud.cerebras.ai", "cerebras", "_guardar_cere"),
            ("groq", "🔵", "Groq", "Comentarista (Vision IA)",
             "groq_key_entry", "gsk_...", "GROQ_API_KEY",
             "https://console.groq.com", "groq", "_guardar_groq"),
            ("google_studio", "🔴", "Google Studio IA", "Chat Bot, Vision IA",
             "google_key_entry", "AIza...", "GOOGLE_STUDIO_API_KEY",
             "https://aistudio.google.com/app/apikey", "google_studio", "_guardar_google"),
        ]:
            card = mk(c)
            card.pack(fill="x", padx=14, pady=(0, 8))
            lb(card, f"{icon}  {title} — {usage}", sz=12, bold=True, col=TXT).pack(anchor="w", padx=14, pady=(10, 4))
            
            # Entry
            entry = ctk.CTkEntry(card, placeholder_text=placeholder_key,
                                font=("Consolas", 12), show="*",
                                fg_color=CARD, text_color=TXT, border_color=BORD)
            entry.pack(fill="x", padx=14, pady=(0, 4))
            val = config.get(cfg_key, "")
            if val:
                entry.insert(0, val)
            setattr(self, entry_attr, entry)
            
            # Botones
            bf = ctk.CTkFrame(card, fg_color="transparent")
            bf.pack(fill="x", padx=14, pady=(4, 4))
            bf.grid_columnconfigure((0, 1, 2), weight=1)
            ctk.CTkButton(bf, text="👁", fg_color=CARD2, text_color=TXT,
                          command=lambda e=entry: self._toggle_key(e),
                          height=30, corner_radius=8, width=40).grid(row=0, column=0, padx=(0, 4))
            ctk.CTkButton(bf, text="💾 Guardar", fg_color=GRN, text_color=GRN_T,
                          command=getattr(self, guardar_fn),
                          height=30, corner_radius=8, hover_color="#10b981").grid(row=0, column=1, padx=2)
            ctk.CTkButton(bf, text="🧪 Test", fg_color=PURP, text_color="#f3e8ff",
                          command=lambda p=test_fn, e=entry: self._test_api(p, e.get()),
                          height=30, corner_radius=8).grid(row=0, column=2, padx=(4, 0))
            
            # Link
            link = lb(card, f"🌐  {link_url}", sz=10, col="#818cf8", cursor="hand2")
            link.pack(anchor="w", padx=14, pady=(2, 4))
            link.bind("<Button-1>", lambda e, u=link_url: webbrowser.open(u))
            
            # Status
            status = config.get(cfg_key, "")
            if status and len(status) > 5:
                lb(card, f"✅ Guardada (****{status[-6:]})", sz=10, col=GRN_T).pack(anchor="w", padx=14, pady=(0, 8))
            else:
                lb(card, "❌ No configurada", sz=10, col=RED_T).pack(anchor="w", padx=14, pady=(0, 8))
        
        return tab
    
    def _toggle_key(self, entry):
        current = entry.cget("show")
        entry.configure(show="" if current == "*" else "*")
    
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
        self.log(f"✅  API Key de Groq guardada correctamente")
    
    def _guardar_google(self):
        value = self.google_key_entry.get().strip()
        if not value:
            self.log("❌  Ingresa una API Key válida")
            return
        if not value.startswith("AIza"):
            self.log("❌  Google Studio API Key debe empezar con 'AIza'")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["GOOGLE_STUDIO_API_KEY"] = value
        save_config(cfg)
        config["GOOGLE_STUDIO_API_KEY"] = value
        self.log(f"✅  Google Studio IA API Key guardada correctamente")
    
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
        
        voice_male_edge = voice_male_display.replace("_", "-")
        voice_female_edge = voice_female_display.replace("_", "-")
        
        _, device_id = self.get_devices()
        
        vol = float(config.get("VOLUME", "2.0"))
        self.log("Probando voz masculina...")
        speak("Hola, esta es una prueba de voz masculina", voice_male_edge, device_id, volume=vol)
        
        import time
        time.sleep(1)
        
        self.log("Probando voz femenina...")
        speak("Hola, esta es una prueba de voz femenina", voice_female_edge, device_id, volume=vol)
    
    def _seleccionar_audio(self, idx, path_var):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title=f"Seleccionar audio #{idx}",
                                          filetypes=[("Audio", "*.mp3 *.wav *.ogg")])
        if path:
            path_var.set(path)
            self.log(f"🔊 Audio #{idx}: {path}")
    
    def _reprobar_audio(self, path):
        if not path:
            self.log("⚠  No hay archivo seleccionado")
            return
        import os
        if not os.path.isfile(path):
            self.log(f"⚠  Archivo no encontrado: {path}")
            return
        from src.audio import play_file
        sp_dev, _ = self.get_devices()
        self.log(f"🔊 Reproduciendo: {os.path.basename(path)} (device {sp_dev})")
        import threading
        def _play():
            try:
                play_file(path, sp_dev)
            except Exception as e:
                self.after(0, lambda: self.log(f"❌ Error reproduciendo: {e}"))
        threading.Thread(target=_play, daemon=True).start()
    
    def _guardar_audio_slots(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        for i, path_var, cmd_var in self._audio_slots:
            cfg[f"AUDIO_FILE_{i}"] = path_var.get()
            cfg[f"AUDIO_CMD_{i}"] = cmd_var.get()
        save_config(cfg)
        for i, path_var, cmd_var in self._audio_slots:
            config[f"AUDIO_FILE_{i}"] = path_var.get()
            config[f"AUDIO_CMD_{i}"] = cmd_var.get()
        self.log("✅  Sonidos guardados")
    
    def _crear_nuevo_prompt(self):
        # Pedir nombre para el nuevo prompt
        dialog = ctk.CTkInputDialog(title="Nueva Personalidad", 
                                    text="Ingresa el nombre para la nueva personalidad:")
        nombre = dialog.get_input()
        if nombre:
            nombre = nombre.strip()
            if not nombre.endswith(".txt"):
                nombre += ".txt"
            
            if nombre in self.prompt_files:
                self.log(f"Ya existe una personalidad con ese nombre")
                return
            
            try:
                ruta = os.path.join(self.prompt_folder, nombre)
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write("Eres una VTuber divertida y amigable.")
                
                self.prompt_files = [f for f in os.listdir(self.prompt_folder) if f.endswith(".txt")]
                self.prompt_files.sort()
                
                self.mode_select.configure(values=self.prompt_files)
                self.mode_select.set(nombre)
                
                from src.core.config import load_config, save_config
                cfg = load_config()
                cfg["SELECTED_PROMPT"] = nombre
                save_config(cfg)
                config["SELECTED_PROMPT"] = nombre
                
                with open(ruta, encoding="utf-8") as f:
                    self.current_prompt = f.read()
                
                self.log(f"Nueva personalidad '{nombre}' creada")
            except Exception as e:
                self.log(f"Error al crear personalidad: {e}")
    
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
                vol = float(config.get("VOLUME", "2.0"))
                speak(r, "es-MX-DaliaNeural", d, volume=vol)
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
            from src.core.config import load_config
            cfg = load_config()
            
            tok = cfg.get("TWITCH_TOKEN", "")
            nick = cfg.get("NICK", "")
            chan = cfg.get("CHANNEL", "")
            
            if not tok or not nick or not chan:
                self.log("Faltan datos tras OAuth (TOKEN/NICK/CHANNEL)")
                return
            sd, idev = self.get_devices()
            slots = []
            for i, pv, cv in self._audio_slots:
                p, c = pv.get(), cv.get()
                if p and c:
                    slots.append((p, c.strip().lower()))

            start_chat(self, tok, nick, chan,
                       cfg.get("GROQ_API_KEY", ""), sd, idev, self,
                       ia_command=cfg.get("BOT_IA_COMMAND", "!IA"),
                       ia_voice=cfg.get("BOT_IA_VOICE", "es-MX-DaliaNeural"),
                       audio_slots=slots)
            self.after(0, lambda: (
                self.twitch_btn.configure(text="🟢  Conectado",
                                          fg_color=GRN, text_color=GRN_T),
            ))
        
        def _on_oauth_success(token, nick, channel):
            self.log(f"✅  OAuth OK — usuario: {nick}")
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
                text="🔴  Twitch", fg_color="#9146FF", text_color="#fff"))
        
        def run():
            tok = config.get("TWITCH_TOKEN", "")
            if tok:
                self.log("🔍  Validando token de Twitch...")
                if not validate_token(tok):
                    self.log("⚠  Token expirado o inválido. Abriendo OAuth...")
                    self.after(0, lambda: self.twitch_btn.configure(
                        text="🟡  Autorizando...",
                        fg_color=AMB, text_color="#fff"))
                    from src.core.oauth_server import clear_token
                    clear_token()
                    tok = None
                else:
                    self.log("🔵  Conectando Twitch con token guardado...")
                    _start_chat_with_current_config()
                    return
            
            if TwitchOAuth is None:
                self.log("❌  oauth_server no disponible (revisa secrets_manager.py)")
                return
            self.log("🌐  Abriendo navegador para autorizar en Twitch...")
            self.after(0, lambda: self.twitch_btn.configure(
                text="🟡  Esperando autorización...",
                fg_color=AMB, text_color="#fff"))
            try:
                TwitchOAuth(on_success=_on_oauth_success,
                            on_error=_on_oauth_error).start()
            except Exception as e:
                self.log(f"❌  No se pudo iniciar OAuth: {e}")
                self.log(traceback.format_exc())
        
        threading.Thread(target=run, daemon=True).start()
    
    def _guardar_config_panel(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        
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
        if hasattr(self, 'mn2'):
            idx = self.mn2.get()
            if idx in ("(Ninguno)", ""):
                cfg.pop("MONITOR_DEVICE", None)
            else:
                try:
                    cfg["MONITOR_DEVICE"] = str(self.dev_names.index(idx) if idx in self.dev_names else 0)
                except:
                    cfg["MONITOR_DEVICE"] = "0"
        
        if hasattr(self, 'ptt_key_entry'):
            ptt_key = self.ptt_key_entry.get().strip().upper()
            if not ptt_key:
                ptt_key = "F9"
            cfg["PTT_KEY"] = ptt_key
            config["PTT_KEY"] = ptt_key
        
        for key, attr in [("IA_NOMBRE", "_ia_nombre"), ("IA_APELLIDO", "_ia_apellido"),
                          ("IA_EDAD", "_ia_edad"), ("IA_GENERO", "_ia_genero"),
                          ("IA_CUMPLE", "_ia_cumple"), ("IA_SIGNO", "_ia_signo"),
                          ("IA_ALTURA", "_ia_altura"), ("IA_TRABAJO", "_ia_trabajo"),
                          ("IA_GUSTOS", "_ia_gustos"), ("IA_FRASES", "_ia_frases"),
                          ("PLAYER_NOMBRE", "_player_nombre"), ("PLAYER_APELLIDO", "_player_apellido"),
                          ("PLAYER_EDAD", "_player_edad"), ("PLAYER_GENERO", "_player_genero"),
                          ("PLAYER_CUMPLE", "_player_cumple"), ("PLAYER_SIGNO", "_player_signo"),
                          ("PLAYER_ALTURA", "_player_altura"), ("PLAYER_TRABAJO", "_player_trabajo"),
                           ("PLAYER_GUSTOS", "_player_gustos"), ("PLAYER_FRASES", "_player_frases"),
                           ("PLAYER_RELACION", "_player_relacion")]:
            if hasattr(self, attr):
                cfg[key] = getattr(self, attr).get()
                config[key] = getattr(self, attr).get()
        
        save_config(cfg)
        self._build_prompt(self._selected_prompt_file)
        self.log(f"Configuracion guardada ({ptt_key if hasattr(self, 'ptt_key_entry') else 'F9'})")
    
    def _borrar_memoria(self):
        try:
            from src.ai.memory import clear_memory
            clear_memory()
            self.log("🗑  Memoria borrada correctamente")
        except Exception as e:
            self.log(f"❌  Error al borrar memoria: {e}")
    
    def change_mode(self, filename):
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["SELECTED_PROMPT"] = filename
        save_config(cfg)
        config["SELECTED_PROMPT"] = filename
        self._build_prompt(filename)
        self.log(f"Personalidad cambiada a: {filename}")

    def _build_prompt(self, filename=None):
        if filename is None:
            filename = self._selected_prompt_file

        def _seccion(attr_prefix, titulo):
            partes = []
            campos = [("Nombre", f"_{attr_prefix}_nombre"), ("Apellido", f"_{attr_prefix}_apellido"),
                      ("Edad", f"_{attr_prefix}_edad"), ("Género", f"_{attr_prefix}_genero"),
                      ("Cumpleaños", f"_{attr_prefix}_cumple"), ("Signo Zodiacal", f"_{attr_prefix}_signo"),
                      ("Altura", f"_{attr_prefix}_altura"), ("Trabajo", f"_{attr_prefix}_trabajo"),
                      ("Gustos", f"_{attr_prefix}_gustos"), ("Frases típicas", f"_{attr_prefix}_frases")]
            if attr_prefix == "player":
                campos.append(("Relación", "_player_relacion"))
            for k, attr in campos:
                if hasattr(self, attr):
                    v = getattr(self, attr).get()
                    if v.strip():
                        partes.append(f"{k}: {v.strip()}")
            if partes:
                return f"[{titulo}]\n" + "\n".join(partes)
            return None

        secciones = [s for s in [_seccion("ia", "Perfil de la IA"), _seccion("player", "Perfil del Streamer / Player")] if s]
        with open(os.path.join(self.prompt_folder, filename), encoding="utf-8") as f:
            personalidad = f.read()
        if secciones:
            self.current_prompt = "\n\n".join(secciones) + f"\n\n[Personalidad]\n{personalidad}"
        else:
            self.current_prompt = personalidad
    
    def get_devices(self):
        sn = self.sp2.get()
        an = self.ia2.get()
        mn = self.mn2.get()
        sid = next((i for n, i in self.devices if n == sn), 2)
        iid = next((i for n, i in self.devices if n == an), 2)
        if mn in ("(Ninguno)", ""):
            return sid, iid
        mid = next((i for n, i in self.devices if n == mn), None)
        return sid, ([iid, mid] if mid and mid != iid else iid)
    
    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
    
    # ════════════════════════════════════════════════════════════════════════
    #  AYUDA
    # ════════════════════════════════════════════════════════════════════════
    def _tab_creditos(self, parent):
        tab = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0,
                                      scrollbar_button_color=PURP, scrollbar_button_hover_color=BORD)
        
        # ── Info del proyecto ──
        card = mk(tab, accent=True)
        card.pack(fill="x", padx=14, pady=(12, 6))
        lb(card, f"{APP_NAME}  v{APP_VERSION}", sz=16, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(card, "Asistente VTuber con IA — Twitch, TTS, STT, Comentarista automático",
           sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 4))
        
        ctk.CTkFrame(card, height=1, fg_color="#2a2a3e").pack(fill="x", padx=14, pady=(6, 6))
        for label, url in [
            ("GitHub",                  "https://github.com/manuel00084"),
            ("Twitch",                  "https://www.twitch.tv/manuel0084"),
            ("Google Studio IA",        "https://aistudio.google.com/app/apikey"),
            ("Groq Console",            "https://console.groq.com/keys"),
            ("Cerebras Cloud",          "https://cloud.cerebras.ai"),
            ("Twitch Developer",        "https://dev.twitch.tv/console"),
        ]:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=1)
            lb(row, label, sz=10, col=MUT, width=120).pack(side="left")
            lnk = lb(row, url, sz=10, col="#818cf8", cursor="hand2")
            lnk.pack(side="left", padx=(8, 0))
            lnk.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()

        # ── Guía rápida ──
        guide = mk(tab, accent=True)
        guide.pack(fill="x", padx=14, pady=(0, 6))
        lb(guide, "📖  Guía rápida", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        items = [
            ("📊  Panel", "Control principal — perfiles, PTT, actividad en vivo y guardado rápido"),
            ("🎧  Audio", "Selecciona dispositivos: Speaker (Bot), IA Voz (TTS) y Monitor (escucha)"),
            ("🗣  Personalidad", "Perfil de la IA + Perfil del Streamer como contexto del prompt"),
            ("🤖  Bot Speaker", "Comandos !sp / !spm. Sube MP3 y asígnales un comando personalizado"),
            ("💬  Chat Bot IA", "IA que responde con voz en Twitch + Comentarista automático del juego"),
            ("🔑  API Keys", "Groq (comentarista), Cerebras (chat), Google Studio (vision/chat)"),
        ]
        for icon_title, desc in items:
            row = ctk.CTkFrame(guide, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            lb(row, icon_title, sz=11, bold=True, col=TXT, width=120).pack(side="left")
            lb(row, desc, sz=9, col=MUT).pack(side="left", padx=(8, 0))
        ctk.CTkFrame(guide, height=6, fg_color="transparent").pack()

        # ── Perfiles ──
        pf = mk(tab)
        pf.pack(fill="x", padx=14, pady=(0, 6))
        lb(pf, "👤  Perfiles de IA y Streamer", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        pf_info = [
            "Perfil de la IA — Nombre, edad, género, altura, gustos, frases típicas, cumpleaños, signo, trabajo",
            "Perfil del Streamer / Player — Mismos campos: nombre, apellido, edad, género, cumpleaños, signo, altura, trabajo",
            "Ambos perfiles se concatenan automáticamente como contexto ANTES del prompt de personalidad",
            "La IA usa estos datos para saber quién es ella y quién es su compañero/player",
            "Cada perfil tiene su botón 💾 Guardar para persistir los datos en config.txt",
            "Los campos se cargan automáticamente al iniciar la aplicación",
        ]
        for t in pf_info:
            lb(pf, f"•  {t}", sz=9, col=MUT).pack(anchor="w", padx=14, pady=1)
        ctk.CTkFrame(pf, height=6, fg_color="transparent").pack()

        # ── Modos del Comentarista ──
        modes = mk(tab)
        modes.pack(fill="x", padx=14, pady=(0, 6))
        lb(modes, "🎮  Comentarista automático", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        lb(modes, "Los módulos se activan con switches y se combinan entre sí:", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))

        mode_details = [
            ("📖 OCR", 
             "Lectura de texto en pantalla con RapidOCR. "
             "Pre-procesa la imagen: upscale 2x, eliminación de glow, CLAHE y sharpen. "
             "Filtra detecciones pequeñas (<4% de la altura) y texto inválido (<4 caracteres, <30% letras). "
             "Si detecta <2 resultados a resolución reducida, reintenta a resolución completa (720p). "
             "El texto se narra con prefijo aleatorio: 'Veo en pantalla:', 'Pone:', 'Dice:', etc."),
            ("⚗ Karin Vision Lite",
             "Detección visual local sin IA externa. Usa OpenCV para: "
             "detección de movimiento por frame difference, "
             "seguimiento de objetos con centroid tracking, "
             "análisis de escenas por templates predefinidos, "
             "y máquina de estados del juego. No requiere API keys."),
            ("🎭 Karin Animadora",
             "Genera comentarios animados y dinámicos basados en la detección visual. "
             "Combina datos de OCR + Karin Vision para producir reacciones más vivas. "
             "Usa la IA de texto (proveedor seleccionado en dropdown) para generar las frases."),
            ("🟢 Groq Vision",
             "Captura la pantalla y envía la imagen a Groq para descripción visual. "
             "Modelo: meta-llama/llama-4-scout-17b-16e-instruct. "
             "Incluye OCR + contexto del juego en el prompt. "
             "Tasa adaptable: 5-15s entre capturas. "
             "Usa la API Key de Groq (gsk_...)."),
            ("🔵 Google Vision",
             "Captura la pantalla y envía la imagen a Gemini para descripción detallada. "
             "Cadena de fallback automática: "
             "gemini-2.0-flash → gemini-2.0-flash-001 → gemini-2.5-flash. "
             "Incluye OCR + contexto del juego. "
             "Usa la API Key de Google Studio (AIza...)."),
        ]
        for icon_title, desc in mode_details:
            row = ctk.CTkFrame(modes, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            lb(row, icon_title, sz=11, bold=True, col=TXT, width=120).pack(side="left", anchor="n")
            lb(row, desc, sz=9, col=MUT, wraplength=400).pack(side="left", padx=(8, 0), fill="x", expand=True)

        lb(modes, "💡 Los módulos se pueden combinar (ej: OCR + Groq Vision). Al togglear, se reinicia el servicio.",
           sz=9, col=MUT).pack(anchor="w", padx=14, pady=(6, 1))
        ctk.CTkFrame(modes, height=6, fg_color="transparent").pack()

        # ── Proveedores de IA ──
        prov = mk(tab)
        prov.pack(fill="x", padx=14, pady=(0, 6))
        lb(prov, "🤖  Proveedores de IA", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        lb(prov, "Cada proveedor tiene su propia API Key y modelos disponibles:", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))

        prov_details = [
            ("🟢 Groq",
             "Texto: llama-3.1-8b-instant (rápido), llama-3.3-70b-versatile (potente). "
             "Visión: meta-llama/llama-4-scout-17b-16e-instruct (único activo). "
             "Usado para: Comentarista, PTT. "
             "Web: console.groq.com/keys — Key: gsk_..."),
            ("🟡 Cerebras",
             "Texto: llama3.1-8b (rápido), qwen-3-235b (MoE, 22B activos), gpt-oss-120b (avanzado). "
             "Sin visión. "
             "Usado para: Chat Bot IA, PTT, Twitch. "
             "Web: cloud.cerebras.ai — Key: csk_..."),
            ("🔴 Google Studio",
             "Texto + Visión: gemini-2.0-flash → gemini-2.0-flash-001 → gemini-2.5-flash (fallback automático). "
             "Usado para: Chat Bot IA, Google Vision. "
             "Web: aistudio.google.com/app/apikey — Key: AIza..."),
        ]
        for icon_title, desc in prov_details:
            row = ctk.CTkFrame(prov, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            lb(row, icon_title, sz=11, bold=True, col=TXT, width=40).pack(side="left", anchor="n")
            lb(row, desc, sz=9, col=MUT, wraplength=460).pack(side="left", padx=(4, 0), fill="x", expand=True)

        lb(prov, "💡 Si un modelo falla (429, 400, 404), se intenta el siguiente en la cadena con backoff progresivo.",
           sz=9, col=MUT).pack(anchor="w", padx=14, pady=(6, 1))
        ctk.CTkFrame(prov, height=6, fg_color="transparent").pack()

        # ── Sistema de Audio ──
        audio = mk(tab)
        audio.pack(fill="x", padx=14, pady=(0, 6))
        lb(audio, "🔊  Sistema de Audio", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))

        audio_details = [
            "Speaker (Bot) — Altavoz principal para comandos !sp / !spm del Bot Speaker en Twitch",
            "IA Voz (TTS) — Dispositivo donde se reproduce la voz del Comentarista IA y Chat Bot",
            "Monitor — Segundo dispositivo opcional: la IA se escucha en Speaker + Monitor simultáneamente",
            "Volumen fijo 2.0 (ya no hay slider). Normalización al 85% para evitar distorsión",
            "Push-To-Talk (PTT) — Mantén F9 (configurable) para hablar, se envía a la IA y responde con voz",
            "Edge TTS — Voces neuronales en español: Dalia, Dario, Lia, Elvira, Emilia, etc.",
        ]
        for t in audio_details:
            lb(audio, f"•  {t}", sz=9, col=MUT).pack(anchor="w", padx=14, pady=1)
        ctk.CTkFrame(audio, height=6, fg_color="transparent").pack()

        # ── Requisitos ──
        req = mk(tab)
        req.pack(fill="x", padx=14, pady=(0, 6))
        lb(req, "⚙️  Requisitos", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        reqs = [
            "Python 3.10 o superior",
            "API Key de al menos un proveedor: Groq (gsk_), Cerebras (csk_) o Google Studio (AIza)",
            "Cuenta de desarrollador en Twitch (dev.twitch.tv) para OAuth y Bot",
            "Modelo Vosk pequeño español (vosk-model-small-es-0.42) para STT / PTT",
            "Windows 10+ (dxcam para captura de pantalla rápida)",
            "Conexión a internet para APIs de IA y TTS",
        ]
        for r in reqs:
            lb(req, f"•  {r}", sz=9, col=MUT).pack(anchor="w", padx=14, pady=1)
        ctk.CTkFrame(req, height=6, fg_color="transparent").pack()

        # ── Licencia ──
        legal = mk(tab)
        legal.pack(fill="x", padx=14, pady=(0, 6))
        lb(legal, "⚖️  Licencia", sz=12, bold=True, col=PURP).pack(anchor="w", padx=12, pady=(10, 2))
        lb(legal, "Apache License 2.0", sz=10, col=MUT).pack(anchor="w", padx=12, pady=(2, 0))
        a_link = lb(legal, "apache.org/licenses/LICENSE-2.0", sz=10, col="#818cf8", cursor="hand2")
        a_link.pack(anchor="w", padx=12, pady=(0, 2))
        a_link.bind("<Button-1>", lambda e: webbrowser.open("http://www.apache.org/licenses/LICENSE-2.0"))
        lb(legal, "Desarrollado por Manuel0084", sz=10, col=MUT).pack(anchor="w", padx=12, pady=(2, 0))
        lb(legal, "Copyright 2024-2026", sz=10, col=MUT).pack(anchor="w", padx=12, pady=(0, 6))

        # ── Third Party ──
        tp = mk(tab)
        tp.pack(fill="x", padx=14, pady=(0, 12))
        lb(tp, "📦  Terceros", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        lb(tp, "Software y modelos de terceros con sus respectivas licencias:",
           sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 4))
        tg = ctk.CTkFrame(tp, fg_color="transparent")
        tg.pack(fill="x", padx=14, pady=(4, 8))
        tg.grid_columnconfigure((0, 1), weight=1)
        third_party = [
            ("Vosk", "Apache 2.0"),
            ("Edge TTS", "Microsoft"),
            ("CustomTkinter", "MIT"),
            ("OpenCV", "Apache 2.0"),
            ("TwitchIO", "MIT"),
            ("RapidOCR (ONNX)", "Apache 2.0"),
            ("ONNX Runtime", "MIT"),
            ("dxcam", "MIT"),
            ("Groq API", "Propietaria"),
            ("Cerebras API", "Propietaria"),
            ("Google Gemini API", "Propietaria"),
            ("Pillow", "Historical"),
        ]
        for i, (lib, lic) in enumerate(third_party):
            r, c = divmod(i, 2)
            lb(tg, f"• {lib}  —  {lic}", sz=10, col=MUT).grid(row=r, column=c, sticky="w", pady=1, padx=(0, 8))

        return tab


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