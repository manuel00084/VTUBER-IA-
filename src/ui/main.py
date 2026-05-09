import customtkinter as ctk
import threading, os, traceback, webbrowser, requests

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

from src.core.config import load_config
from src.audio import audio_worker, speak, stop_audio, get_output_devices
from src.ai import ask_groq, ask_cerebras, ask_ai
from src.bot.twitch_bot import start_chat
from src.core.oauth_server import TwitchOAuth, validate_token
from src.utils.ptt import PTTManager
from src.utils.game_watcher import GameWatcher
from src.utils import PIL_OK
from src.utils.translator import TranslatorManager

config = load_config()

# ── Paleta ───────────────────────────────────────────────────────────────────
BG     = "#1a1b2e"; SIDE   = "#16172a"; CARD  = "#1e2035"; CARD2 = "#252641"
BORD   = "#2e3060"; PURP   = "#6441a5"
GRN    = "#166534"; GRN_T  = "#bbf7d0"
RED    = "#7f1d1d"; RED_T  = "#fca5a5"
BLU    = "#1e3a5f"; BLU_T  = "#93c5fd"
AMB    = "#78350f"; AMB_T  = "#fcd34d"
TXT    = "#e2e8f0"; MUT    = "#94a3b8"; LOGBG = "#0f1117"

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
        super().__init__()
        self.title("VTuber AI")
        self.geometry("920x650")
        self.minsize(880, 580)
        self.configure(fg_color=BG)

        threading.Thread(target=audio_worker, daemon=True).start()

        # Prompts
        self.prompt_folder = os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
        os.makedirs(self.prompt_folder, exist_ok=True)
        self.prompt_files = [f for f in os.listdir(self.prompt_folder) if f.endswith(".txt")]
        if not self.prompt_files:
            p = os.path.join(self.prompt_folder, "default.txt")
            open(p, "w", encoding="utf-8").write("Eres una VTuber divertida.")
            self.prompt_files = ["default.txt"]
        with open(os.path.join(self.prompt_folder, self.prompt_files[0]), encoding="utf-8") as f:
            self.current_prompt = f.read()

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
        self.game_watcher = None
        self.translator   = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()

        # PTT
        if PTTManager:
            try:
                self.ptt_obj = PTTManager(
                    app=self, ask_ai_fn=ask_ai, speak=speak,
                    stop_audio=stop_audio, config=config,
                    get_devices=self.get_devices,
                    current_prompt=lambda: self.current_prompt,
                    key="f9", voice="es-MX-DaliaNeural")
                self.log("⌨  PTT listo — mantén F9 para hablar")
            except Exception as e:
                self.log(f"⚠  PTT error: {e}")
        else:
            self.log("⚠  PTT no disponible — pip install keyboard")

        if not PIL_OK:
            self.log("⚠  Comentarista: pip install pillow")

    # ════════════════════════════════════════════════════════════════════════
    #  SIDEBAR
    # ════════════════════════════════════════════════════════════════════════
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=SIDE, corner_radius=0, width=200)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(8, weight=1)

        hdr = ctk.CTkFrame(sb, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(16, 4))
        lb(hdr, "🎭  VTuber AI", sz=15, bold=True).pack(anchor="w")
        lb(hdr, "Groq + Edge TTS", sz=10, col=MUT).pack(anchor="w")

        ctk.CTkFrame(sb, height=1, fg_color=BORD).grid(row=1, column=0, sticky="ew", padx=8)

        self._nav_btns = {}
        for i, (txt, key) in enumerate([
            ("🖥  Panel",        "panel"),
            ("🔊  Audio",        "audio"),
            ("🈳  Traductor",    "traductor"),
            ("🎤  Voz PTT",      "ptt"),
            ("🤖  IA",          "ia_config"),
        ]):
            b = ctk.CTkButton(sb, text=txt, anchor="w", fg_color="transparent",
                              text_color=MUT, hover_color=CARD2, font=("Arial", 12),
                              corner_radius=8, height=34,
                              command=lambda k=key: self._tab(k))
            b.grid(row=3+i, column=0, sticky="ew", padx=6, pady=1)
            self._nav_btns[key] = b

        ctk.CTkFrame(sb, height=1, fg_color=BORD).grid(row=8, column=0, sticky="ew", padx=8, pady=6)

        self.twitch_btn = ctk.CTkButton(
            sb, text="🟣  Conectar Twitch", fg_color=PURP, text_color="#fff",
            hover_color="#7c58c0", font=("Arial", 12, "bold"), corner_radius=8,
            height=34, command=self.connect_twitch)
        self.twitch_btn.grid(row=10, column=0, padx=8, pady=(0, 4), sticky="ew")

        c = ctk.CTkLabel(sb, text="twitch.tv/manuel0084", font=("Arial", 10),
                         text_color=MUT, cursor="hand2")
        c.grid(row=11, column=0, pady=(0, 12))
        c.bind("<Button-1>", lambda e: webbrowser.open("https://www.twitch.tv/manuel0084"))

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
        area.grid(row=1, column=0, sticky="nsew")
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)

        self._tabs = {
            "panel":        self._tab_panel(area),
            "audio":        self._tab_audio(area),
            "traductor":    self._tab_traductor(area),
            "ptt":          self._tab_ptt(area),
            "ia_config":    self._tab_ia_config(area),
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
        lb(cp, "🎭  Personalidad", sz=11, bold=True, col=MUT).pack(anchor="w", padx=10, pady=(8, 2))
        lb(cp, "Prompt", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(2, 0))
        self.mode_select = cb(cp, self.prompt_files, command=self.change_mode)
        self.mode_select.pack(fill="x", padx=10, pady=(0, 3)); self.mode_select.set(self.prompt_files[0])

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
        lb(cv, "🎤  PTT — F9", sz=11, bold=True, col=MUT).pack(anchor="w", padx=10, pady=(8, 4))
        inf = mk(cv, fg_color=CARD)
        inf.pack(fill="x", padx=10, pady=(0, 4))
        ir = ctk.CTkFrame(inf, fg_color="transparent")
        ir.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(ir, text=" F9 ", font=("Consolas", 12, "bold"),
                     fg_color=BORD, text_color=TXT, corner_radius=5).pack(side="left", padx=(0, 8))
        lb(ir, "Mantén para hablar", sz=11, col=MUT).pack(side="left")
        br = ctk.CTkFrame(cv, fg_color="transparent")
        br.pack(fill="x", padx=10, pady=(0, 8))
        br.grid_columnconfigure((0, 1), weight=1)
        bt(br, "🎤 Hablar", GRN,  GRN_T,    self.ptt_click, h=32).grid(row=0, column=0, padx=(0, 3), sticky="ew")
        bt(br, "🤖 Test",  PURP, "#e9d5ff", self.test_ia,   h=32).grid(row=0, column=1, padx=(3, 0), sticky="ew")

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
        return tab

    # ════════════════════════════════════════════════════════════════════════
    #  TAB TRADUCTOR
    # ════════════════════════════════════════════════════════════════════════
    def _tab_traductor(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🈳  Traductor en tiempo real", sz=12, bold=True).pack(anchor="w", padx=10, pady=(10, 6))

        # Traducir a + Motor
        opt_row = ctk.CTkFrame(c, fg_color="transparent")
        opt_row.pack(fill="x", padx=10, pady=(0, 6))
        lb(opt_row, "Traducir a:", sz=11, col=MUT).pack(side="left", padx=(0, 6))
        self.idioma_var = ctk.StringVar(value="español")
        cb(opt_row, ["español", "inglés", "portugués", "francés", "alemán"],
           variable=self.idioma_var).pack(side="left", padx=(0, 12))
        lb(opt_row, "Motor:", sz=11, col=MUT).pack(side="left", padx=(0, 6))
        self.trad_motor = ctk.CTkOptionMenu(opt_row, values=["Groq (OCR)", "Google", "DeepL", "LibreTranslate", "MyMemory"],
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
    #  TAB COMENTARISTA
    # ════════════════════════════════════════════════════════════════════════
    def _tab_comentarista(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🎮  Comentarista de juego", sz=12, bold=True).pack(anchor="w", padx=10, pady=(10, 2))
        lb(c, "Analiza la pantalla con IA y comenta en voz real.", sz=10, col=MUT).pack(
            anchor="w", padx=10, pady=(0, 8))

        self.watcher_status = ctk.CTkLabel(
            c, text="⭕  INACTIVO",
            font=("Arial", 13, "bold"), text_color="#f87171",
            fg_color=CARD2, corner_radius=8)
        self.watcher_status.pack(fill="x", padx=10, pady=(0, 8))

        sr = ctk.CTkFrame(c, fg_color="transparent")
        sr.pack(fill="x", padx=10, pady=(0, 6))
        lb(sr, "Comentar cada:", sz=11, col=MUT).pack(side="left")
        self.watcher_intervalo = ctk.IntVar(value=30)
        self._wlbl2 = lb(sr, "30s", sz=11, bold=True)
        ctk.CTkSlider(sr, from_=10, to=120, number_of_steps=22,
                      variable=self.watcher_intervalo, fg_color=BORD,
                      progress_color=GRN, button_color=GRN, button_hover_color="#22c55e",
                      command=self._sync_wlbl).pack(side="left", fill="x", expand=True, padx=8)
        self._wlbl2.pack(side="left", padx=(0, 4))

        lb(c, "📋  Log en tiempo real:", sz=10, col=MUT).pack(anchor="w", padx=10, pady=(4, 0))
        self.watcher_log = ctk.CTkTextbox(
            c, height=140, font=("Consolas", 11),
            fg_color=LOGBG, text_color="#86efac",
            border_width=0, corner_radius=6)
        self.watcher_log.pack(fill="x", padx=10, pady=(2, 8))

        self.btn_watcher2 = bt(c, "▶  INICIAR COMENTARISTA", GRN, GRN_T,
                               self.toggle_watcher, h=46)
        self.btn_watcher2.pack(fill="x", padx=10, pady=(0, 10))

        inf = mk(tab, fg_color=CARD2)
        inf.pack(fill="x", padx=14, pady=(0, 10))
        lb(inf, "ℹ  Requisitos:", sz=11, bold=True).pack(anchor="w", padx=10, pady=(8, 2))
        lb(inf, "• pip install pillow\n• GROQ_API_KEY en config.txt\n"
                "• Modelo con visión: llama-4-scout (automático)",
           sz=10, col=MUT, justify="left").pack(anchor="w", padx=10, pady=(0, 10))

        return tab

    # ════════════════════════════════════════════════════════════════════════
    #  TAB PTT
    # ════════════════════════════════════════════════════════════════════════
    def _tab_ptt(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🎤  Voz PTT — Push to Talk", sz=12, bold=True).pack(anchor="w", padx=10, pady=(10, 6))
        inf = mk(c, fg_color=CARD2)
        inf.pack(fill="x", padx=10, pady=(0, 8))
        ir = ctk.CTkFrame(inf, fg_color="transparent")
        ir.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(ir, text=" F9 ", font=("Consolas", 14, "bold"),
                     fg_color=BORD, text_color=TXT, corner_radius=6).pack(side="left", padx=(0, 10))
        lb(ir, "Mantén presionado para hablar con la IA", sz=12, col=MUT).pack(side="left")
        br = ctk.CTkFrame(c, fg_color="transparent")
        br.pack(fill="x", padx=10, pady=(0, 10))
        br.grid_columnconfigure((0, 1), weight=1)
        bt(br, "🎤  Hablar ahora", GRN,  GRN_T,    self.ptt_click, h=44).grid(row=0, column=0, padx=(0, 4), sticky="ew")
        bt(br, "🤖  Test IA",     PURP, "#e9d5ff", self.test_ia,   h=44).grid(row=0, column=1, padx=(4, 0), sticky="ew")
        return tab

    # ════════════════════════════════════════════════════════════════════════
    #  TAB IA CONFIG
    # ════════════════════════════════════════════════════════════════════════
    def _tab_ia_config(self, parent):
        tab = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        c = mk(tab)
        c.pack(fill="x", padx=14, pady=(12, 6))
        lb(c, "🤖  Configuración de IA", sz=13, bold=True).pack(anchor="w", padx=10, pady=(12, 4))

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
        self.log(f"✅  GOOGLE_API_KEY guardada correctamente")

    def _test_api(self, provider, api_key):
        if not api_key:
            self.log(f"❌  Primero guarda la API Key")
            return
        self.log(f"🧪  Probando {provider}...")
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

    # ════════════════════════════════════════════════════════════════════════
    #  LÓGICA
    # ════════════════════════════════════════════════════════════════════════
    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def wlog(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.watcher_log.insert("end", text + "\n")
        self.watcher_log.see("end")

    def _sync_wlbl(self, v):
        t = f"{int(v)}s"
        self._wlbl.configure(text=t)
        self._wlbl2.configure(text=t)

    def get_devices(self):
        sn = self.speaker_select.get()
        an = self.ia_select.get()
        mn = self.monitor_select.get()
        sid = next((i for n, i in self.devices if n == sn), 0)
        iid = next((i for n, i in self.devices if n == an), 0)
        if mn in ("(Ninguno)", ""):
            return sid, iid
        mid = next((i for n, i in self.devices if n == mn), None)
        return sid, ([iid, mid] if mid and mid != iid else iid)

    def change_mode(self, filename):
        with open(os.path.join(self.prompt_folder, filename), encoding="utf-8") as f:
            self.current_prompt = f.read()
        self.log(f"🎭  Prompt: {filename}")

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
                from stt import listen
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
            tok  = config.get("TWITCH_TOKEN", "")
            nick = config.get("NICK", "")
            chan = config.get("CHANNEL", "")
            if not tok or not nick or not chan:
                self.log("❌  Faltan datos tras OAuth (TOKEN/NICK/CHANNEL)")
                return
            sd, idev = self.get_devices()
            start_chat(self, tok, nick, chan,
                       config.get("GROQ_API_KEY", ""), sd, idev, self)
            # Actualizar UI desde el hilo principal
            self.after(0, lambda: (
                self.twitch_btn.configure(text="🟣  Conectado",
                                          fg_color=GRN, text_color=GRN_T),
            ))

        def _on_oauth_success(token, nick, channel):
            self.log(f"✅  OAuth OK — usuario: {nick}")
            # Recargar config.txt (oauth_server ya lo guardó)
            try:
                from config import load_config as _lc
                fresh = _lc()
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
    def toggle_watcher(self):
        if self.game_watcher and self.game_watcher.activo:
            self.game_watcher.detener()
            self.game_watcher = None
            for b in [self.btn_watcher, self.btn_watcher2]:
                b.configure(text="▶  Iniciar comentarista", fg_color=GRN, text_color=GRN_T)
            self.watcher_status.configure(text="⭕  INACTIVO", text_color="#f87171")
        else:
            if not GW_OK:
                self.wlog("❌  game_watcher.py no disponible — pip install pillow")
                return
            api_key = config.get("GROQ_API_KEY", "")
            if not api_key:
                self.wlog("❌  Falta GROQ_API_KEY en config.txt")
                return
            iv = int(self.watcher_intervalo.get())
            self.game_watcher = GameWatcher(
                api_key=api_key,
                speak_fn=speak, stop_audio_fn=stop_audio,
                get_devices_fn=self.get_devices,
                current_prompt_fn=lambda: self.current_prompt,
                intervalo=iv, voice="es-MX-DaliaNeural",
                log_fn=self.wlog)
            self.game_watcher.iniciar()
            for b in [self.btn_watcher, self.btn_watcher2]:
                b.configure(text="⏹  Detener comentarista", fg_color=RED, text_color=RED_T)
            self.watcher_status.configure(
                text=f"🟢  ACTIVO — cada {iv}s", text_color="#4ade80")

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
        if hasattr(self, 'speaker_select'):
            idx = self.speaker_select.get()
            try:
                cfg["SPEAKER_DEVICE"] = str(self.dev_names.index(idx) if idx in self.dev_names else 0)
            except:
                cfg["SPEAKER_DEVICE"] = "0"
        if hasattr(self, 'ia_select'):
            idx = self.ia_select.get()
            try:
                cfg["IA_DEVICE"] = str(self.dev_names.index(idx) if idx in self.dev_names else 0)
            except:
                cfg["IA_DEVICE"] = "0"
        save_config(cfg)
        self.log("💾  Configuración guardada correctamente")

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