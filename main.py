"""
main.py  —  VTuber IA (con OAuth Twitch de 1 clic)
"""
import customtkinter as ctk
import threading
import os
import traceback
import webbrowser

try:
    from config import load_config, save_config
except Exception as e:
    print("Error config:", e)
    load_config = lambda: {}
    save_config = lambda x: None

try:
    from audio import audio_worker, speak, stop_audio
except Exception as e:
    print("Error audio:", e)
    def audio_worker(): pass
    def speak(*a, **k): print("speak fallback:", a)
    def stop_audio(): pass

try:
    from ia import ask_groq
except Exception as e:
    print("Error ia:", e)
    def ask_groq(*a, **k): return "IA no disponible"

try:
    from devices import get_output_devices
except Exception as e:
    print("Error devices:", e)
    def get_output_devices(): return [("Default", 0)]

try:
    from twitch_bot import start_chat
except Exception as e:
    print("Error twitch_bot:", e)
    def start_chat(*a, **k): print("Twitch deshabilitado")

try:
    from ptt import PTTManager
except Exception as e:
    print("Error ptt:", e)
    PTTManager = None

try:
    from oauth_server import TwitchOAuth
    OAUTH_AVAILABLE = True
except Exception as e:
    print("OAuth no disponible:", e)
    OAUTH_AVAILABLE = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

PURPLE = "#9B59B6"; PURPLE_DRK = "#7D3C98"; PINK = "#E91E8C"
DARK_BG = "#1A1A2E"; CARD_BG = "#16213E"; ENTRY_BG = "#0F3460"
GREEN_OK = "#2ECC71"; RED_ERR = "#E74C3C"
TEXT_WHITE = "#EAEAEA"; TEXT_GRAY = "#A0A0C0"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VTuber IA")
        self.geometry("540x820")
        self.configure(fg_color=DARK_BG)
        self._config = load_config()
        threading.Thread(target=audio_worker, daemon=True).start()

        self.promt_folder = os.path.join(os.path.dirname(__file__), "PROMT")
        os.makedirs(self.promt_folder, exist_ok=True)
        self.promt_files = [f for f in os.listdir(self.promt_folder) if f.endswith(".txt")]
        if not self.promt_files:
            with open(os.path.join(self.promt_folder, "default.txt"), "w", encoding="utf-8") as f:
                f.write("Eres una VTuber divertida.")
            self.promt_files = ["default.txt"]
        self.current_prompt = "Eres una VTuber divertida."

        self._build_ui()
        self._init_ptt()
        self.after(300, self._check_groq_key)

    def _build_ui(self):
        ctk.CTkLabel(self, text="🎀  VTuber IA",
                     font=("Georgia", 22, "bold"), text_color=PINK).pack(pady=(20, 4))

        # ── Groq API Key ──────────────────────────────────────────────────
        groq_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=14)
        groq_frame.pack(padx=20, pady=(8, 4), fill="x")
        ctk.CTkLabel(groq_frame, text="🤖  Groq API Key  (IA gratuita)",
                     font=("Helvetica", 13, "bold"), text_color=PURPLE).pack(anchor="w", padx=16, pady=(12, 4))
        self._groq_var = ctk.StringVar(value=self._config.get("GROQ_API_KEY", ""))
        self._groq_entry = ctk.CTkEntry(groq_frame, textvariable=self._groq_var,
            placeholder_text="gsk_...", show="•",
            fg_color=ENTRY_BG, border_color=PURPLE, text_color=TEXT_WHITE,
            corner_radius=8, height=36)
        self._groq_entry.pack(padx=16, fill="x")
        row = ctk.CTkFrame(groq_frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 10))
        ctk.CTkButton(row, text="💾 Guardar key", fg_color=PURPLE, hover_color=PURPLE_DRK,
            corner_radius=8, height=30, width=130, font=("Helvetica", 11),
            command=self._save_groq_key).pack(side="left")
        ctk.CTkButton(row, text="🔗 Conseguir Groq key gratis",
            fg_color="transparent", hover_color=ENTRY_BG, text_color=PINK,
            corner_radius=8, height=30, font=("Helvetica", 11),
            command=lambda: webbrowser.open("https://console.groq.com/keys")).pack(side="left", padx=8)

        # ── Twitch OAuth ──────────────────────────────────────────────────
        twitch_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=14)
        twitch_frame.pack(padx=20, pady=4, fill="x")
        ctk.CTkLabel(twitch_frame, text="🎮  Cuenta de Twitch",
                     font=("Helvetica", 13, "bold"), text_color=PURPLE).pack(anchor="w", padx=16, pady=(12, 6))
        self._twitch_lbl = ctk.CTkLabel(twitch_frame, text="● No conectado",
            font=("Helvetica", 12), text_color=RED_ERR)
        self._twitch_lbl.pack(padx=16, anchor="w")
        self._oauth_btn = ctk.CTkButton(twitch_frame,
            text="🔑  Conectar con Twitch  (1 clic)",
            font=("Helvetica", 14, "bold"),
            fg_color="#6441A5", hover_color="#4B317E",
            corner_radius=10, height=46, command=self._start_oauth)
        self._oauth_btn.pack(padx=16, pady=(8, 4), fill="x")
        ctk.CTkLabel(twitch_frame,
            text="Se abre tu navegador → inicias sesión → ¡listo! Sin copiar tokens.",
            font=("Helvetica", 10), text_color=TEXT_GRAY).pack(padx=16, pady=(0, 12))

        # ── Iniciar bot ───────────────────────────────────────────────────
        self._connect_btn = ctk.CTkButton(self,
            text="🔌  Iniciar bot de chat",
            font=("Helvetica", 13, "bold"),
            fg_color=PURPLE, hover_color=PURPLE_DRK,
            corner_radius=10, height=40, command=self.connect_twitch, state="disabled")
        self._connect_btn.pack(padx=20, pady=(8, 3), fill="x")

        ctk.CTkButton(self, text="🎤  Hablar con IA  (F9)",
            font=("Helvetica", 12), fg_color=CARD_BG, hover_color="#1E3A5F",
            corner_radius=10, height=36, command=self.ptt_click).pack(padx=20, pady=3, fill="x")

        # ── Logs ─────────────────────────────────────────────────────────
        self.logs = ctk.CTkTextbox(self, height=150,
            fg_color="#0D0D1A", text_color="#C8F7C5",
            font=("Courier", 11), corner_radius=10)
        self.logs.pack(padx=20, pady=8, fill="x")

        # ── Dispositivos ──────────────────────────────────────────────────
        dev_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        dev_frame.pack(padx=20, pady=4, fill="x")
        ctk.CTkLabel(dev_frame, text="🔊  Audio",
                     font=("Helvetica", 12, "bold"), text_color=PURPLE).pack(anchor="w", padx=14, pady=(10, 4))
        self.devices = get_output_devices()
        device_names = [name for name, _ in self.devices]
        for label_text, attr in [("Bot Speaker:", "speaker_select"), ("IA / VTuber:", "ia_select")]:
            r = ctk.CTkFrame(dev_frame, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(r, text=label_text, width=100,
                         font=("Helvetica", 11), text_color=TEXT_GRAY).pack(side="left")
            combo = ctk.CTkComboBox(r, values=device_names, width=300)
            combo.pack(side="left")
            setattr(self, attr, combo)
        r = ctk.CTkFrame(dev_frame, fg_color="transparent")
        r.pack(fill="x", padx=14, pady=(2, 10))
        ctk.CTkLabel(r, text="Monitor:", width=100,
                     font=("Helvetica", 11), text_color=TEXT_GRAY).pack(side="left")
        self.monitor_select = ctk.CTkComboBox(r, values=["(Ninguno)"] + device_names, width=300)
        self.monitor_select.pack(side="left")
        self.monitor_select.set("(Ninguno)")
        if device_names:
            self.speaker_select.set(device_names[0])
            self.ia_select.set(device_names[0])

        # ── Prompt ───────────────────────────────────────────────────────
        pf = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        pf.pack(padx=20, pady=4, fill="x")
        ctk.CTkLabel(pf, text="🎭  Personalidad",
                     font=("Helvetica", 12, "bold"), text_color=PURPLE).pack(anchor="w", padx=14, pady=(10, 4))
        self.mode_select = ctk.CTkComboBox(pf, values=self.promt_files,
                                           command=self.change_mode, width=360)
        self.mode_select.pack(padx=14, pady=(0, 10))
        self.mode_select.set(self.promt_files[0])
        self.change_mode(self.promt_files[0])

        # ── Créditos ─────────────────────────────────────────────────────
        lbl = ctk.CTkLabel(self, text="💜  Créditos: Manuel0084  |  twitch.tv/manuel0084",
                           font=("Helvetica", 11), text_color=TEXT_GRAY, cursor="hand2")
        lbl.pack(pady=10)
        lbl.bind("<Button-1>", lambda e: webbrowser.open("https://www.twitch.tv/manuel0084"))

    def _init_ptt(self):
        self.ptt = None
        if PTTManager is not None:
            try:
                self.ptt = PTTManager(app=self, ask_groq=ask_groq, speak=speak,
                    stop_audio=stop_audio, config=self._config, get_devices=self.get_devices,
                    current_prompt=lambda: self.current_prompt, key="f9", voice="es-MX-DaliaNeural")
                self.log("⌨️  PTT listo — mantén F9 para hablar")
            except Exception as e:
                self.log(f"⚠️  PTT: {e}")
        else:
            self.log("⚠️  PTT no disponible — instala: pip install keyboard")

    def _check_groq_key(self):
        key = self._config.get("GROQ_API_KEY", "").strip()
        if key:
            self.log("✅  Groq API Key encontrada.")
            self._update_connect_btn()
        else:
            self.log("💡  Ingresa tu Groq API Key arriba (es gratis).")
        token = self._config.get("TWITCH_TOKEN", "").strip()
        nick  = self._config.get("NICK", "").strip()
        if token and nick:
            self._on_twitch_connected(nick)

    def _save_groq_key(self):
        key = self._groq_var.get().strip()
        if not key:
            self.log("❌  La key no puede estar vacía.")
            return
        self._config["GROQ_API_KEY"] = key
        save_config(self._config)
        self.log("✅  Groq API Key guardada.")
        self._update_connect_btn()

    def _start_oauth(self):
        if not OAUTH_AVAILABLE:
            self.log("❌  oauth_server.py no encontrado.")
            return
        from oauth_server import CLIENT_ID
        if CLIENT_ID == "TU_CLIENT_ID_AQUI":
            self.log("❌  Configura CLIENT_ID y CLIENT_SECRET en oauth_server.py")
            return
        self.log("🌐  Abriendo Twitch en el navegador...")
        self._oauth_btn.configure(text="⏳  Esperando autorización...", state="disabled")
        oauth = TwitchOAuth(
            on_success=self._on_twitch_auth_success,
            on_error=lambda msg: self.after(0, self.log, f"❌  {msg}"),
        )
        oauth.start()

    def _on_twitch_auth_success(self, token, nick, channel):
        self._config["TWITCH_TOKEN"] = token
        self._config["NICK"]         = nick
        self._config["CHANNEL"]      = channel
        save_config(self._config)
        self.after(0, self._on_twitch_connected, nick)

    def _on_twitch_connected(self, nick):
        self._twitch_lbl.configure(text=f"● Conectado como {nick}", text_color=GREEN_OK)
        self._oauth_btn.configure(text=f"✅  {nick} — volver a conectar", state="normal")
        self._update_connect_btn()
        self.log(f"🎉  Twitch autenticado como {nick}")

    def _update_connect_btn(self):
        token = self._config.get("TWITCH_TOKEN", "").strip()
        key   = self._config.get("GROQ_API_KEY", "").strip()
        self._connect_btn.configure(state="normal" if token and key else "disabled")

    def log(self, text):
        self.logs.insert("end", text + "\n")
        self.logs.see("end")

    def ptt_click(self):
        def run():
            from stt import listen
            stop_audio()
            self.log("🎤  Escuchando...")
            text = listen()
            if not text:
                self.log("❌  No se entendió")
                return
            self.log(f"🗣️  Tú: {text}")
            respuesta = ask_groq(text, self._config.get("GROQ_API_KEY", ""), self.current_prompt)
            self.log(f"🤖  IA: {respuesta}")
            _, ia_dev = self.get_devices()
            speak(respuesta, "es-MX-DaliaNeural", ia_dev)
        threading.Thread(target=run, daemon=True).start()

    def get_devices(self):
        sn = self.speaker_select.get(); ia = self.ia_select.get(); mo = self.monitor_select.get()
        sid  = next((i for n, i in self.devices if n == sn), 0)
        iaid = next((i for n, i in self.devices if n == ia), 0)
        if mo == "(Ninguno)": return sid, iaid
        mid = next((i for n, i in self.devices if n == mo), None)
        return sid, ([iaid, mid] if mid and mid != iaid else iaid)

    def change_mode(self, filename):
        with open(os.path.join(self.promt_folder, filename), "r", encoding="utf-8") as f:
            self.current_prompt = f.read()
        self.log(f"🎭  Prompt: {filename}")

    def connect_twitch(self):
        def run():
            token   = self._config.get("TWITCH_TOKEN", "")
            nick    = self._config.get("NICK", "")
            channel = self._config.get("CHANNEL", "")
            api_key = self._config.get("GROQ_API_KEY", "")
            if not token:
                self.log("❌  Primero conecta tu cuenta de Twitch.")
                return
            self.log(f"🔌  Iniciando bot en #{channel}...")
            speaker_dev, ia_dev = self.get_devices()
            try:
                start_chat(self, token, nick, channel, api_key, speaker_dev, ia_dev, self)
                self.after(0, self.log, f"✅  Bot activo en #{channel}")
            except Exception as e:
                self.after(0, self.log, f"❌  Error: {e}")
        threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception:
        print("\n========== ERROR AL INICIAR ==========")
        traceback.print_exc()
        print("======================================")
        input("\nPresiona ENTER para cerrar...")
