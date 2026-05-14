import customtkinter as ctk
import threading, os, traceback, webbrowser, requests, base64, time, json
try:
    import keyboard
    KEYBOARD_OK = True
except ImportError:
    KEYBOARD_OK = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_VERSION = "0.9.0-beta"
APP_NAME = "Karin VTuber -IA-"

from src.core.config import load_config
from src.audio import audio_worker, speak, stop_audio, get_output_devices
from src.ai import ask_groq, ask_cerebras, ask_ai
from src.bot.twitch_bot import start_chat, get_twitch_messages, is_chat_ia_activo
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
            self._ia_idx = ia_idx
        else:
            self._ia_default = self.dev_names[0] if self.dev_names else "Default"
            self._ia_idx = 0
        
        self.game_watcher = None
        self.lector_subtitulos = None
        self.player_ia = None
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
        for r in range(10):
            sb.grid_rowconfigure(r, weight=1 if r == 9 else 0)
        
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
        

        
        # Área tabs
        area = ctk.CTkFrame(wrap, fg_color=BG, corner_radius=0)
        area.grid(row=1, column=0, sticky="nsew")
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)
        
        # Definir todas las voces para usar en el panel
        self.voices_all = ["es-ES-ElviraNeural", "es-ES-AlvaroNeural",
                           "es-MX-DaliaNeural", "es-MX-LiaNeural", "es-MX-DarioNeural",
                           "es-AR-EmiliaNeural", "es-AR-TonoNeural"]
        
        self._tabs = {
            "panel":        self._tab_panel(area),
            "audio":        self._tab_audio(area),
            "bot_speaker":  self._tab_bot_speaker(area),
            "comentarista": self._tab_comentarista(area),
            "player_ia":    self._tab_player_ia(area),
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
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        
        # Log con acento
        lc = mk(tab, accent=True)
        lc.pack(fill="x", padx=14, pady=(12, 6))
        lb(lc, "📋  Actividad", sz=11, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        self.log_box = ctk.CTkTextbox(lc, height=120, font=("Consolas", 11),
                                      fg_color=LOGBG, text_color="#7dd3fc",
                                      border_width=0, corner_radius=6)
        self.log_box.pack(fill="x", padx=14, pady=(0, 12))
        
        # Grid 2 columnas
        g = ctk.CTkFrame(tab, fg_color="transparent")
        g.pack(fill="both", expand=True, padx=14, pady=4)
        g.grid_columnconfigure((0, 1), weight=1)
        g.grid_rowconfigure((0, 1), weight=1)
        
        # Personalidad
        cp = mk(g, accent=True)
        cp.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))
        lb(cp, "Personalidad", sz=11, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        lb(cp, "Prompt activo", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(2, 0))
        self.mode_select = cb(cp, self.prompt_files, command=self.change_mode)
        self.mode_select.pack(fill="x", padx=14, pady=(0, 3))
        initial_prompt = config.get("SELECTED_PROMPT", self.prompt_files[0])
        if initial_prompt not in self.prompt_files:
            initial_prompt = self.prompt_files[0]
        self.mode_select.set(initial_prompt)
        
        btn_new_prompt = ctk.CTkButton(cp, text="+ Nueva Personalidad",
                                       fg_color=CARD2, text_color=TXT,
                                       hover_color=PURP, height=28, corner_radius=8,
                                       command=self._crear_nuevo_prompt)
        btn_new_prompt.pack(fill="x", padx=14, pady=(6, 4))
        
        bp = ctk.CTkFrame(cp, fg_color="transparent")
        bp.pack(fill="x", padx=14, pady=(6, 10))
        bp.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(bp, text="🗑  Borrar memoria", fg_color=RED, text_color=RED_T,
                      hover_color="#ef4444", height=32, corner_radius=8,
                      command=self._borrar_memoria).grid(row=0, column=0, padx=(0, 3), sticky="ew")
        ctk.CTkButton(bp, text="💾 Guardar config", fg_color=GRN, text_color=GRN_T,
                      hover_color="#10b981", height=32, corner_radius=8,
                      command=self._guardar_config_panel).grid(row=0, column=1, padx=(3, 0), sticky="ew")
        
        # PTT rápido
        cv = mk(g, accent=True)
        cv.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=(0, 5))
        lb(cv, "🎤  Push-to-Talk", sz=11, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 4))
        inf = mk(cv)
        inf.pack(fill="x", padx=14, pady=(0, 4))
        ir = ctk.CTkFrame(inf, fg_color="transparent")
        ir.pack(fill="x", padx=10, pady=8)
        lb(ir, "CTRL +", sz=11, col=TXT).pack(side="left", padx=(0, 4))
        self.ptt_key_entry = ctk.CTkEntry(ir, width=60, font=("Consolas", 12, "bold"),
                                           fg_color=BG, text_color=TXT, border_color=BORD,
                                           justify="center")
        self.ptt_key_entry.pack(side="left", padx=(0, 8))
        saved_ptt_key = config.get("PTT_KEY", "F9")
        self.ptt_key_entry.insert(0, saved_ptt_key)
        lb(ir, "Mantén para hablar", sz=10, col=MUT).pack(side="left")
        br = ctk.CTkFrame(cv, fg_color="transparent")
        br.pack(fill="x", padx=14, pady=(4, 10))
        bt(br, "🎤 Hablar", GRN, GRN_T, self.ptt_click, h=34).pack(fill="x")
        
        return tab
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB AUDIO
    # ════════════════════════════════════════════════════════════════════════
    def _tab_audio(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        
        c = mk(tab, accent=True)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🔊  Dispositivos de audio", sz=12, bold=True).pack(anchor="w", padx=14, pady=(10, 4))
        for txt, attr, default in [
            ("Bot Speaker", "sp2", self._sp_default),
            ("IA Voz", "ia2", self._ia_default),
            ("Monitor", "mn2", self._sp_default),
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
        
        # Equalizador
        eq_frame = mk(tab, accent=True)
        eq_frame.pack(fill="x", padx=14, pady=(12, 6))
        lb(eq_frame, "🎛  Equalizador de voz IA", sz=12, bold=True).pack(anchor="w", padx=14, pady=(10, 4))
        lb(eq_frame, "Ajusta graves, agudos, velocidad y auto-tune de la voz", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))
        
        eq_inner = ctk.CTkFrame(eq_frame, fg_color="transparent")
        eq_inner.pack(fill="x", padx=14, pady=(0, 10))
        
        for label, var_name, attr, from_, to_, steps, suffix, col_label in [
            ("🎸 Graves (Bass)", "EQ_BASS", "bass_var", -12, 12, 24, "", MUT),
            ("🎵 Agudos (Treble)", "EQ_TREBLE", "treble_var", -12, 12, 24, "", MUT),
            ("⚡ Velocidad", "EQ_SPEED", "speed_var", -50, 50, 100, "%", MUT),
            ("🎤 Auto-Tune", "EQ_AUTOTUNE", "autotune_var", 0, 100, 100, "%", MUT),
        ]:
            row = ctk.CTkFrame(eq_inner, fg_color="transparent")
            row.pack(fill="x", pady=2)
            lb(row, label, sz=10, col=col_label, width=110).pack(side="left")
            var = ctk.IntVar(value=config.get(var_name, 0))
            setattr(self, attr, var)
            slider = ctk.CTkSlider(row, from_=from_, to=to_, number_of_steps=steps,
                                   variable=var, fg_color=CARD, progress_color=BORD)
            slider.pack(side="left", fill="x", expand=True, padx=(8, 8))
            lb(row, f"{var.get()}{suffix}", sz=9, col=MUT, width=35).pack(side="right")
        
        eq_btn = ctk.CTkButton(eq_frame, text="💾 Guardar EQ", fg_color=GRN, text_color=GRN_T,
                              height=30, corner_radius=8, hover_color="#10b981",
                              command=self._guardar_eq)
        eq_btn.pack(padx=14, pady=(0, 10))
        
        return tab
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB BOT SPEAKER
    # ════════════════════════════════════════════════════════════════════════
    def _tab_bot_speaker(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        
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
            row.grid_columnconfigure(2, weight=1)
            
            lb(row, f"#{i}:", sz=10, col=MUT, width=20).grid(row=0, column=0)
            
            path_var = ctk.StringVar(value=config.get(f"AUDIO_FILE_{i}", ""))
            entry_path = ctk.CTkEntry(row, textvariable=path_var,
                                       font=("Consolas", 10), fg_color=CARD, text_color=MUT,
                                       border_color="#2a2a3e", state="readonly", width=200)
            entry_path.grid(row=0, column=1, padx=(4, 4))
            
            cmd_var = ctk.StringVar(value=config.get(f"AUDIO_CMD_{i}", ""))
            entry_cmd = ctk.CTkEntry(row, textvariable=cmd_var, placeholder_text="!comando",
                                      font=("Consolas", 11, "bold"), width=100,
                                      fg_color=CARD, text_color=TXT, border_color=BORD)
            entry_cmd.grid(row=0, column=2, sticky="ew", padx=(0, 4))
            
            ctk.CTkButton(row, text="📂", fg_color=CARD2, text_color=TXT, width=30, height=26,
                          corner_radius=5, command=lambda idx=i, pv=path_var: self._seleccionar_audio(idx, pv)).grid(row=0, column=3, padx=(0, 2))
            ctk.CTkButton(row, text="▶", fg_color=CARD2, text_color=GRN_T, width=30, height=26,
                          corner_radius=5, command=lambda pv=path_var: self._reprobar_audio(pv.get())).grid(row=0, column=4)
            
            self._audio_slots.append((i, path_var, cmd_var))
        
        ctk.CTkButton(audio_card, text="💾 Guardar sonidos", fg_color=GRN, text_color=GRN_T,
                      height=30, corner_radius=8, hover_color="#10b981",
                      command=self._guardar_audio_slots).pack(padx=14, pady=(0, 10))
        
        return tab
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB CHAT BOT IA
    # ════════════════════════════════════════════════════════════════════════
    def _tab_comentarista(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        
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
        
        lb(ia_grid, "Voz TTS:", sz=11, col=MUT).grid(row=1, column=0, sticky="w", pady=(6, 0))
        voz_row = ctk.CTkFrame(ia_grid, fg_color="transparent")
        voz_row.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
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
                      command=self._guardar_ia_command).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(10, 0))
        
        # ── Comentarista ──
        c = mk(tab, accent=True)
        c.pack(fill="x", padx=14, pady=(8, 6))
        lb(c, "🎮  Comentarista IA", sz=13, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(c, "Analiza la pantalla y comenta el juego automáticamente", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))
        
        opts = mk(c)
        opts.pack(fill="x", padx=14, pady=(0, 10))
        
        grid = ctk.CTkFrame(opts, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(10, 4))
        grid.grid_columnconfigure((0, 1), weight=1)
        
        lb(grid, "Juego:", sz=11, col=MUT).grid(row=0, column=0, sticky="w", pady=3)
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
        
        lb(grid, "Intervalo (seg):", sz=11, col=MUT).grid(row=1, column=0, sticky="w", pady=3)
        irow = ctk.CTkFrame(grid, fg_color="transparent")
        irow.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.comentarista_intervalo = ctk.CTkEntry(irow, placeholder_text="30",
                                                    fg_color=CARD, text_color=TXT, border_color=BORD,
                                                    font=("Segoe UI", 11), width=80)
        self.comentarista_intervalo.pack(side="left")
        self.comentarista_intervalo.insert(0, str(config.get("COMENTARISTA_INTERVALO", 30)))
        
        lb(grid, "Voz:", sz=11, col=MUT).grid(row=2, column=0, sticky="w", pady=3)
        self.comentarista_voice = ctk.CTkComboBox(grid, values=self.voices_all,
                                                    fg_color=CARD, button_color=PURP,
                                                    dropdown_fg_color=CARD2, text_color=TXT,
                                                    border_color=BORD, font=("Segoe UI", 11))
        self.comentarista_voice.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.comentarista_voice.set(config.get("COMENTARISTA_VOICE", "es-MX-DaliaNeural"))
        
        lb(grid, "Modo analisis:", sz=11, col=MUT).grid(row=3, column=0, sticky="w", pady=3)
        self.comentarista_modo = ctk.CTkComboBox(grid, 
            values=[
                "OCR (Solo Lectura)",
                "OpenCV + OCR + IA",
                "Groq Vision (Máxima Exp)",
                "Groq Vision (Exp máxima)"
            ],
            fg_color=CARD, button_color=PURP,
            dropdown_fg_color=CARD2, text_color=TXT,
            border_color=BORD, font=("Segoe UI", 11))
        self.comentarista_modo.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)
        modo_guardado = config.get("COMENTARISTA_MODO", "OpenCV + OCR + IA")
        self.comentarista_modo.set(modo_guardado)
        
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
        
        # Botón EasyOCR toggle
        btn_frame2 = ctk.CTkFrame(c, fg_color="transparent")
        btn_frame2.pack(fill="x", padx=14, pady=(0, 10))
        eocr_off = config.get("EASYOCR_DISABLED", "0") == "1"
        self.easyocr_toggle = ctk.CTkButton(btn_frame2,
            text="🧠 EasyOCR: OFF (0MB)" if eocr_off else "🧠 EasyOCR: ON (500MB)",
            fg_color=RED if eocr_off else GRN,
            text_color=RED_T if eocr_off else GRN_T,
            font=("Segoe UI", 11, "bold"), corner_radius=8, height=30,
            command=self._toggle_easyocr)
        self.easyocr_toggle.pack(fill="x")
        
        c_log_frame = mk(tab)
        c_log_frame.pack(fill="both", expand=True, padx=14, pady=(8, 12))
        lb(c_log_frame, "📋  Log del Comentarista", sz=10, bold=True, col=MUT).pack(anchor="w", padx=10, pady=(6, 2))
        self.comentarista_log = ctk.CTkTextbox(c_log_frame, fg_color=LOGBG, text_color=TXT,
                                                font=("Consolas", 10), height=170)
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
            import requests
            try:
                r = requests.get("https://api.cerebras.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"}, timeout=10)
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
    
    def _iniciar_comentarista(self):
        modo = self.comentarista_modo.get()
        juego = self.juego_entry.get().strip()
        voz = self.comentarista_voice.get()
        
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["COMENTARISTA_JUEGO"] = juego
        cfg["COMENTARISTA_VOICE"] = voz
        cfg["COMENTARISTA_MODO"] = modo
        save_config(cfg)
        for k, v in cfg.items():
            config[k] = v
        
        usar_groq = "Groq" in modo
        usar_ia = "IA" in modo
        solo_lectura = "Solo Lectura" in modo
        
        ia_key = ""
        groq_key = ""
        if usar_groq:
            groq_key = cfg.get("GROQ_API_KEY", "")
            if not groq_key:
                self.log("❌  Se necesita GROQ_API_KEY para Groq Vision")
                return
        elif usar_ia:
            ia_key = cfg.get("CEREBRAS_API_KEY", "")
            if ia_key:
                self.log("🤖  Cerebras disponible para comentarios IA")
            else:
                self.log("ℹ️  OpenCV + OCR sin IA (reglas fijas)")
        
        if self.game_watcher:
            self.game_watcher.detener()
        
        self.game_watcher = GameWatcher(
            speak_fn=speak,
            stop_audio_fn=stop_audio,
            get_devices_fn=lambda: self.get_devices(),
            log_fn=self._log_comentarista
        )
        self.game_watcher.iniciar(voz=voz, juego=juego, modo=modo, groq_key=ia_key, solo_lectura=solo_lectura)
        self.log(f"🎮 Comentarista iniciado ({modo})")
    
    def _detener_comentarista(self):
        if self.game_watcher:
            self.game_watcher.detener()
            self.game_watcher = None
        self.log("⏹ Comentarista detenido")
    
    def _iniciar_player_ia(self):
        from src.core.config import load_config, save_config
        
        player_activo = self.player_activo.get()
        modo = self.player_modo.get()
        juego_tipo = self.player_juego.get()
        
        cfg = load_config()
        cfg["PLAYER_ACTIVO"] = player_activo
        cfg["PLAYER_MODO"] = modo
        cfg["PLAYER_JUEGO"] = juego_tipo
        save_config(cfg)
        for k, v in cfg.items():
            config[k] = v
        
        if self.player_ia:
            self.player_ia.detener()
        
        self.player_ia = PlayerIAGamer(
            modo=modo,
            juego_tipo=juego_tipo,
            player_activo=player_activo,
            log_fn=self._log_player_ia
        )
        
        self.player_ia.iniciar()
        self._log_player_ia(f"🎮 Player IA iniciado ({player_activo} - {modo} - {juego_tipo})")
    
    def _detener_player_ia(self):
        if self.player_ia:
            self.player_ia.detener()
            self.player_ia = None
        self._log_player_ia("⏹ Player IA detenido")
    
    def _pausar_player_ia(self):
        if self.player_ia:
            if self.player_ia._pausado:
                self.player_ia.reanudar()
                self._log_player_ia("▶ Player IA REANUDADO")
            else:
                self.player_ia.pausar()
                self._log_player_ia("⏸ Player IA PAUSADO")
    
    def _guardar_config_comentarista(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["COMENTARISTA_JUEGO"] = self.juego_entry.get().strip()
        cfg["COMENTARISTA_INTERVALO"] = int(self.comentarista_intervalo.get().strip() or 30)
        cfg["COMENTARISTA_VOICE"] = self.comentarista_voice.get()
        cfg["COMENTARISTA_MODO"] = self.comentarista_modo.get()
        cfg.pop("SUBTITULOS_INTERVALO", None)
        cfg.pop("PLAYER_MODO", None)
        cfg.pop("PLAYER_INPUT", None)
        cfg.pop("PLAYER_JUEGO", None)
        save_config(cfg)
        for k, v in cfg.items():
            config[k] = v
        self.log("✅ Configuración del comentarista guardada")
    
    def _toggle_easyocr(self):
        estado = config.get("EASYOCR_DISABLED", "0")
        if estado == "1":
            config["EASYOCR_DISABLED"] = "0"
            self.easyocr_toggle.configure(text="🧠 EasyOCR: ON (500MB)", fg_color=GRN, text_color=GRN_T)
            self.log("🧠 EasyOCR activado - recargar módulo si es necesario")
        else:
            config["EASYOCR_DISABLED"] = "1"
            self.easyocr_toggle.configure(text="🧠 EasyOCR: OFF (0MB)", fg_color=RED, text_color=RED_T)
            self.log("🧠 EasyOCR desactivado - ahorrando ~500MB RAM")
        from src.core.config import save_config
        cfg = load_config()
        cfg["EASYOCR_DISABLED"] = config["EASYOCR_DISABLED"]
        save_config(cfg)

    def _guardar_ia_command(self):
        cmd = self.ia_cmd_entry.get().strip()
        voz = self.ia_voice_menu.get()
        if not cmd:
            self.log("❌  Ingresa un comando válido")
            return
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["BOT_IA_COMMAND"] = cmd
        cfg["BOT_IA_VOICE"] = voz
        save_config(cfg)
        config["BOT_IA_COMMAND"] = cmd
        config["BOT_IA_VOICE"] = voz
        self.log(f"✅  Comando IA guardado: {cmd} → voz: {voz}")

    def _test_ia_voice(self):
        voz = self.ia_voice_menu.get()
        from src.audio import speak
        speak("Hola, soy tu asistente de voz. Esta es una prueba.", voz, 0)

    def _log_comentarista(self, msg):
        self.comentarista_log.insert("end", f"{msg}\n")
        self.comentarista_log.see("end")
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB PLAYER IA
    # ════════════════════════════════════════════════════════════════════════
    def _tab_player_ia(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        
        c = mk(tab, accent=True)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🎯  Player IA Gamer", sz=13, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(c, "La IA juega automáticamente analizando la pantalla en tiempo real", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 6))
        
        opts = mk(c)
        opts.pack(fill="x", padx=14, pady=(0, 10))
        
        grid = ctk.CTkFrame(opts, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(10, 4))
        grid.grid_columnconfigure((1, 3, 5), weight=1)
        
        lb(grid, "Jugador:", sz=11, col=MUT).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.player_activo = ctk.CTkComboBox(grid, values=["Player 1", "Player 2", "Ambos"],
                                              fg_color=CARD, button_color=PURP,
                                              dropdown_fg_color=CARD2, text_color=TXT,
                                              border_color=BORD, font=("Segoe UI", 11))
        self.player_activo.grid(row=0, column=1, sticky="ew")
        self.player_activo.set(config.get("PLAYER_ACTIVO", "Player 1"))
        
        lb(grid, "Modo:", sz=11, col=MUT).grid(row=0, column=2, sticky="w", padx=(12, 6))
        self.player_modo = ctk.CTkComboBox(grid, values=["basico", "intermedio", "avanzado"],
                                           fg_color=CARD, button_color=PURP,
                                           dropdown_fg_color=CARD2, text_color=TXT,
                                           border_color=BORD, font=("Segoe UI", 11))
        self.player_modo.grid(row=0, column=3, sticky="ew")
        self.player_modo.set(config.get("PLAYER_MODO", "basico"))
        
        lb(grid, "Tipo:", sz=11, col=MUT).grid(row=0, column=4, sticky="w", padx=(12, 6))
        self.player_juego = ctk.CTkComboBox(grid, values=["accion", "lucha", "rpg", "plataforma", "hack_slash"],
                                            fg_color=CARD, button_color=PURP,
                                            dropdown_fg_color=CARD2, text_color=TXT,
                                            border_color=BORD, font=("Segoe UI", 11))
        self.player_juego.grid(row=0, column=5, sticky="ew")
        self.player_juego.set(config.get("PLAYER_JUEGO", "accion"))
        
        # Info: controles
        info_frame = mk(c)
        info_frame.pack(fill="x", padx=14, pady=(0, 10))
        lb(info_frame, "🎮  Controles", sz=11, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(8, 2))
        lb(info_frame, "Cargados desde config/Keyboard.txt y config/Gamepad.txt", sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 4))
        lb(info_frame, "📁  Keyboard.txt — Teclas para P1 y P2    |    🎮  Gamepad.txt — Mapeo de botones", sz=10, col=GRN_T).pack(anchor="w", padx=14, pady=(2, 8))
        
        # Modos
        info_modos = mk(c)
        info_modos.pack(fill="x", padx=14, pady=(0, 10))
        lb(info_modos, "📖  Modos disponibles", sz=11, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(8, 2))
        for txt in [
            "• Básico: Movimiento automático + ataque simple",
            "• Intermedio: IA con decisiones (combatir, loot, explorar)",
            "• Avanzado: IA con aprendizaje y estrategias",
        ]:
            lb(info_modos, txt, sz=10, col=MUT).pack(anchor="w", padx=14, pady=(1, 0))
        ctk.CTkFrame(info_modos, height=4, fg_color="transparent").pack()
        
        # Botones
        btns = ctk.CTkFrame(c, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=(0, 10))
        btns.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        self.player_btn = ctk.CTkButton(btns, text="▶ Iniciar", fg_color=GRN, text_color=GRN_T,
            font=("Segoe UI", 12, "bold"), corner_radius=10, height=38,
            command=self._iniciar_player_ia)
        self.player_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        
        ctk.CTkButton(btns, text="⏹ Detener", fg_color=RED, text_color=RED_T,
            font=("Segoe UI", 12, "bold"), corner_radius=10, height=38,
            command=self._detener_player_ia).grid(row=0, column=1, padx=(4, 4), sticky="ew")
        
        ctk.CTkButton(btns, text="⏸ Pausar", fg_color=AMB, text_color=AMB_T,
            font=("Segoe UI", 11), corner_radius=10, height=38,
            command=self._pausar_player_ia).grid(row=0, column=2, padx=(4, 4), sticky="ew")
        
        ctk.CTkButton(btns, text="💾 Guardar", fg_color=BLU, text_color=BLU_T,
            font=("Segoe UI", 11), corner_radius=10, height=38,
            command=self._guardar_config_player_ia).grid(row=0, column=3, padx=(4, 0), sticky="ew")
        
        # Log
        c_log_frame = mk(tab)
        c_log_frame.pack(fill="both", expand=True, padx=14, pady=(8, 12))
        lb(c_log_frame, "📋  Log del Player IA", sz=10, bold=True, col=MUT).pack(anchor="w", padx=10, pady=(6, 2))
        self.player_log = ctk.CTkTextbox(c_log_frame, fg_color=LOGBG, text_color=TXT,
                                         font=("Consolas", 10), height=130)
        self.player_log.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        
        return tab
    
    def _build_keyboard_config(self):
        for widget in self.keys_container.winfo_children():
            widget.destroy()
        
        lb(self.keys_container, "⌨️ Player 1 (Teclado):", sz=11, bold=True).pack(anchor="w", pady=(8, 4))
        
        keys_p1 = [
            ("Derecha:", "KEY_P1_DERECHA", "d"),
            ("Izquierda:", "KEY_P1_IZQUIERDA", "a"),
            ("Arriba:", "KEY_P1_ARRIBA", "w"),
            ("Abajo:", "KEY_P1_ABAJO", "s"),
            ("Saltar:", "KEY_P1_SALTAR", "space"),
            ("Atacar:", "KEY_P1_ATACAR", "j"),
            ("Defender:", "KEY_P1_DEFENDER", "k"),
            ("Recoger:", "KEY_P1_RECOGER", "e"),
            ("Correr:", "KEY_P1_CORRER", "shift"),
            ("Menú:", "KEY_P1_MENU", "tab"),
            ("Pausa:", "KEY_P1_PAUSA", "esc"),
            ("Especial:", "KEY_P1_ESPECIAL", "u"),
        ]
        
        self.key_entries_p1 = {}
        for i, (label, key_name, default) in enumerate(keys_p1):
            row = ctk.CTkFrame(self.keys_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            lb(row, label, sz=10).pack(side="left", padx=(0, 8))
            entry = ctk.CTkEntry(row, placeholder_text=default, width=80, fg_color=CARD, text_color=TXT, border_color=BORD)
            entry.pack(side="left", padx=2)
            entry.insert(0, config.get(key_name, default))
            self.key_entries_p1[key_name] = entry
        
        lb(self.keys_container, "⌨️ Player 2 (Teclado):", sz=11, bold=True).pack(anchor="w", pady=(12, 4))
        
        keys_p2 = [
            ("Derecha:", "KEY_P2_DERECHA", "right"),
            ("Izquierda:", "KEY_P2_IZQUIERDA", "left"),
            ("Arriba:", "KEY_P2_ARRIBA", "up"),
            ("Abajo:", "KEY_P2_ABAJO", "down"),
            ("Saltar:", "KEY_P2_SALTAR", "num2"),
            ("Atacar:", "KEY_P2_ATACAR", "."),
            ("Defender:", "KEY_P2_DEFENDER", "/"),
            ("Recoger:", "KEY_P2_RECOGER", "p"),
            ("Correr:", "KEY_P2_CORRER", "rshift"),
            ("Menú:", "KEY_P2_MENU", "home"),
            ("Pausa:", "KEY_P2_PAUSA", "end"),
            ("Especial:", "KEY_P2_ESPECIAL", "insert"),
        ]
        
        self.key_entries_p2 = {}
        for i, (label, key_name, default) in enumerate(keys_p2):
            row = ctk.CTkFrame(self.keys_container, fg_color="transparent")
            row.pack(fill="x", pady=2)
            lb(row, label, sz=10).pack(side="left", padx=(0, 8))
            entry = ctk.CTkEntry(row, placeholder_text=default, width=80, fg_color=CARD, text_color=TXT, border_color=BORD)
            entry.pack(side="left", padx=2)
            entry.insert(0, config.get(key_name, default))
            self.key_entries_p2[key_name] = entry
    
    def _build_gamepad_config(self):
        for widget in self.keys_container.winfo_children():
            widget.destroy()
        
        lb(self.keys_container, "🎮 Configuración Gamepad Detectada", sz=11, bold=True).pack(anchor="w", pady=(8, 4))
        
        lb(self.keys_container, "El gamepad se detectará automáticamente al iniciar", sz=10, col=GRN_T).pack(anchor="w", pady=(4, 4))
        
        gamepad_info = mk(self.keys_container, fg_color=CARD2)
        gamepad_info.pack(fill="x", padx=10, pady=(8, 8))
        
        lb(gamepad_info, "🎯 Mapeo de botones Gamepad:", sz=11, bold=True).pack(anchor="w", padx=10, pady=(8, 4))
        lb(gamepad_info, "• Stick Izq. = Movimiento (WASD)", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(gamepad_info, "• A (botón 0) = Atacar", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(gamepad_info, "• B (botón 1) = Defender", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(gamepad_info, "• X (botón 2) = Saltar", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(gamepad_info, "• Y (botón 3) = Especial", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(gamepad_info, "• LB (botón 4) = Recoger", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(gamepad_info, "• RB (botón 5) = Correr", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        lb(gamepad_info, "• Start = Menú | Select = Pausa", sz=10, col=TXT).pack(anchor="w", padx=10, pady=(2, 0))
        
        lb(gamepad_info, "💡 Consejo: Conecta el gamepad antes de iniciar", sz=10, col=AMB_T).pack(anchor="w", padx=10, pady=(8, 4))
    
    def _cambiar_input_type(self, event=None):
        input_type = self.player_input.get()
        if input_type == "keyboard":
            self._build_keyboard_config()
        else:
            self._build_gamepad_config()
    
    def _guardar_config_player_ia(self):
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["PLAYER_ACTIVO"] = self.player_activo.get()
        cfg["PLAYER_MODO"] = self.player_modo.get()
        cfg["PLAYER_INPUT"] = self.player_input.get()
        cfg["PLAYER_JUEGO"] = self.player_juego.get()
        
        if hasattr(self, 'key_entries_p1') and self.player_input.get() == "keyboard":
            for key_name, entry in self.key_entries_p1.items():
                cfg[key_name] = entry.get().strip().lower()
            for key_name, entry in self.key_entries_p2.items():
                cfg[key_name] = entry.get().strip().lower()
        
        save_config(cfg)
        for k, v in cfg.items():
            config[k] = v
        self.log("✅ Configuración del Player IA guardada")
    
    def _log_player_ia(self, msg):
        self.player_log.insert("end", f"{msg}\n")
        self.player_log.see("end")
    
    # ════════════════════════════════════════════════════════════════════════
    #  TAB API_KEY
    # ════════════════════════════════════════════════════════════════════════
    def _tab_api_key(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        
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
        self.log(f"✅  GROQ_API_KEY guardada correctamente")
    
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
        
        self.log("Probando voz masculina...")
        speak("Hola, esta es una prueba de voz masculina", voice_male_edge, device_id)
        
        import time
        time.sleep(1)
        
        self.log("Probando voz femenina...")
        speak("Hola, esta es una prueba de voz femenina", voice_female_edge, device_id)
    
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
        from src.audio import play_file
        _, dev = self.get_devices()
        if isinstance(dev, list):
            dev = dev[0]
        self.log(f"🔊 Reproduciendo: {path}")
        import threading
        threading.Thread(target=play_file, args=(path, dev), daemon=True).start()
    
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
                       cfg.get("GROQ_API_KEY", ""), sd, idev, self,
                       ia_command=cfg.get("BOT_IA_COMMAND", "!IA"),
                       ia_voice=cfg.get("BOT_IA_VOICE", "es-MX-DaliaNeural"))
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
    
    def change_mode(self, filename):
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg["SELECTED_PROMPT"] = filename
        save_config(cfg)
        config["SELECTED_PROMPT"] = filename
        with open(os.path.join(self.prompt_folder, filename), encoding="utf-8") as f:
            self.current_prompt = f.read()
        self.log(f"Personalidad cambiada a: {filename}")
    
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
    
    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
    
    def wlog(self, text):
        self.log(text)
    
    # ════════════════════════════════════════════════════════════════════════
    #  AYUDA
    # ════════════════════════════════════════════════════════════════════════
    def _tab_creditos(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        
        # ── Info + Enlaces ──
        card = mk(tab, accent=True)
        card.pack(fill="x", padx=14, pady=(12, 6))
        lb(card, f"{APP_NAME}  v{APP_VERSION}", sz=15, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        lb(card, "Asistente VTuber con inteligencia artificial — Twitch, TTS, STT, Comentarista",
           sz=10, col=MUT).pack(anchor="w", padx=14, pady=(0, 4))
        
        ctk.CTkFrame(card, height=1, fg_color="#2a2a3e").pack(fill="x", padx=14, pady=(6, 6))
        for label, url in [
            ("Repositorio GitHub",      "https://github.com/manuel00084"),
            ("Canal de Twitch",         "https://www.twitch.tv/manuel0084"),
            ("Groq Console",            "https://console.groq.com/keys"),
            ("Cerebras Cloud",          "https://cloud.cerebras.ai"),
            ("Twitch Developer",        "https://dev.twitch.tv/console"),
            ("Apache License 2.0",      "http://www.apache.org/licenses/LICENSE-2.0"),
        ]:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=1)
            lb(row, label, sz=10, col=MUT, width=130).pack(side="left")
            lnk = lb(row, url, sz=10, col="#818cf8", cursor="hand2")
            lnk.pack(side="left", padx=(8, 0))
            lnk.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()

        # ── Licencia ──
        legal = mk(tab)
        legal.pack(fill="x", padx=14, pady=(0, 6))
        lb(legal, "⚖️  Licencia", sz=12, bold=True, col=PURP).pack(anchor="w", padx=12, pady=(10, 2))
        lb(legal, "Apache License 2.0", sz=10, col=MUT).pack(anchor="w", padx=12, pady=(2, 0))
        a_link = lb(legal, "apache.org/licenses/LICENSE-2.0", sz=10, col="#818cf8", cursor="hand2")
        a_link.pack(anchor="w", padx=12, pady=(0, 2))
        a_link.bind("<Button-1>", lambda e: webbrowser.open("http://www.apache.org/licenses/LICENSE-2.0"))
        lb(legal, "Desarrollado por Manuel0084", sz=10, col=MUT).pack(anchor="w", padx=12, pady=(2, 0))
        lb(legal, "Copyright 2024", sz=10, col=MUT).pack(anchor="w", padx=12, pady=(0, 6))

        # ── Third Party ──
        tp = mk(tab)
        tp.pack(fill="x", padx=14, pady=(0, 12))
        lb(tp, "📦  Third Party", sz=12, bold=True, col=PURP).pack(anchor="w", padx=14, pady=(10, 2))
        lb(tp, "Este proyecto utiliza software y modelos de terceros con sus respectivas licencias:",
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
            ("PyTorch", "BSD"),
            ("EasyOCR", "Apache 2.0"),
            ("ONNX Runtime", "MIT"),
            ("dxcam", "MIT"),
            ("Groq / Cerebras API", "Propietaria"),
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