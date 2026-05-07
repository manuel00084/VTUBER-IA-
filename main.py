import customtkinter as ctk
import threading
import os
import traceback
import webbrowser

# ===== IMPORTS SEGUROS =====
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
    def speak(*args, **kwargs): print("speak fallback:", args)
    def stop_audio(): pass

try:
    from ia import ask_groq
except Exception as e:
    print("Error ia:", e)
    def ask_groq(*args, **kwargs): return "IA no disponible"

try:
    from devices import get_output_devices
except Exception as e:
    print("Error devices:", e)
    def get_output_devices(): return [("Default", 0)]

try:
    from twitch_bot import start_chat
except Exception as e:
    print("Error twitch_bot:", e)
    def start_chat(*args, **kwargs): print("Twitch deshabilitado")

try:
    from ptt import PTTManager
except Exception as e:
    print("Error ptt:", e)
    PTTManager = None

try:
    from game_watcher import GameWatcher
except Exception as e:
    print("Error game_watcher:", e)
    GameWatcher = None

try:
    from translator import TranslatorManager
except Exception as e:
    print("Error translator:", e)
    TranslatorManager = None

config = load_config()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VTuber AI - ESTABLE")
        self.geometry("540x980")

        threading.Thread(target=audio_worker, daemon=True).start()

        # ===== PROMPTS =====
        self.promt_folder = os.path.join(os.path.dirname(__file__), "PROMT")
        os.makedirs(self.promt_folder, exist_ok=True)
        self.promt_files = [f for f in os.listdir(self.promt_folder) if f.endswith(".txt")]

        if not self.promt_files:
            default_path = os.path.join(self.promt_folder, "default.txt")
            with open(default_path, "w", encoding="utf-8") as f:
                f.write("Eres una VTuber divertida.")
            self.promt_files = ["default.txt"]

        self.current_prompt = "Eres una VTuber divertida."

        # ===== UI =====
        ctk.CTkLabel(self, text="Sistema iniciado (modo estable)").pack(pady=8)

        self.logs = ctk.CTkTextbox(self, height=160)
        self.logs.pack(pady=8, padx=10, fill="x")

        ctk.CTkButton(self, text="Test GUI",        command=self.test_log).pack(pady=2)
        ctk.CTkButton(self, text="Test Voz",        command=self.test_voice).pack(pady=2)
        ctk.CTkButton(self, text="Test IA",         command=self.test_ia).pack(pady=2)
        ctk.CTkButton(self, text="Conectar Twitch", command=self.connect_twitch).pack(pady=6)
        ctk.CTkButton(self, text="🎤 Hablar con IA", command=self.ptt_click).pack(pady=2)

        # ===== DISPOSITIVOS =====
        self.devices = get_output_devices()
        device_names = [name for name, i in self.devices]

        ctk.CTkLabel(self, text="🔊 Bot Speaker").pack(pady=2)
        self.speaker_select = ctk.CTkComboBox(self, values=device_names)
        self.speaker_select.pack(pady=2)

        ctk.CTkLabel(self, text="🤖 IA Voz (cable virtual / VMagic)").pack(pady=2)
        self.ia_select = ctk.CTkComboBox(self, values=device_names)
        self.ia_select.pack(pady=2)

        ctk.CTkLabel(self, text="🎧 Monitor (tus auriculares)").pack(pady=2)
        self.monitor_select = ctk.CTkComboBox(self, values=["(Ninguno)"] + device_names)
        self.monitor_select.pack(pady=2)
        self.monitor_select.set("(Ninguno)")

        if device_names:
            self.speaker_select.set(device_names[0])
            self.ia_select.set(device_names[0])

        # ===== PROMPT =====
        ctk.CTkLabel(self, text="🎭 Prompt IA").pack(pady=2)
        self.mode_select = ctk.CTkComboBox(self, values=self.promt_files, command=self.change_mode)
        self.mode_select.pack(pady=2)
        self.mode_select.set(self.promt_files[0])
        self.change_mode(self.promt_files[0])

        # ===== GAME WATCHER =====
        self.game_watcher = None
        ctk.CTkLabel(self, text="🎮 Comentarista de Juego").pack(pady=(10, 2))

        frame_watcher = ctk.CTkFrame(self)
        frame_watcher.pack(pady=2)
        ctk.CTkLabel(frame_watcher, text="Cada cuántos segundos:").pack(side="left", padx=5)
        self.intervalo_var = ctk.StringVar(value="30")
        ctk.CTkEntry(frame_watcher, textvariable=self.intervalo_var, width=60).pack(side="left", padx=5)

        self.btn_watcher = ctk.CTkButton(
            self, text="▶ Iniciar Comentarista",
            command=self.toggle_watcher, fg_color="green")
        self.btn_watcher.pack(pady=4)

        # ===== TRADUCTOR =====
        self.translator = None
        ctk.CTkLabel(self, text="🈳 Traductor en Tiempo Real",
                     font=("Arial", 13, "bold")).pack(pady=(14, 2))

        # Idioma destino
        frame_idioma = ctk.CTkFrame(self)
        frame_idioma.pack(pady=2)
        ctk.CTkLabel(frame_idioma, text="Traducir a:").pack(side="left", padx=6)
        self.idioma_var = ctk.StringVar(value="español")
        idioma_menu = ctk.CTkComboBox(
            frame_idioma,
            values=["español", "inglés", "portugués", "francés", "alemán"],
            variable=self.idioma_var,
            width=130
        )
        idioma_menu.pack(side="left", padx=4)

        # Intervalo continuo
        frame_trad_int = ctk.CTkFrame(self)
        frame_trad_int.pack(pady=2)
        ctk.CTkLabel(frame_trad_int, text="Intervalo continuo (seg):").pack(side="left", padx=6)
        self.trad_intervalo_var = ctk.StringVar(value="4")
        ctk.CTkEntry(frame_trad_int, textvariable=self.trad_intervalo_var, width=55).pack(side="left", padx=4)

        # Leer en voz
        self.leer_voz_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self, text="🔊 Leer traducción en voz",
                        variable=self.leer_voz_var).pack(pady=2)

        # Botones del traductor
        frame_btns = ctk.CTkFrame(self)
        frame_btns.pack(pady=4, padx=10, fill="x")

        ctk.CTkButton(
            frame_btns, text="📷 Capturar área\n(traducir una vez)",
            command=self.trad_area_unica, width=120, height=48
        ).pack(side="left", padx=4, pady=4)

        ctk.CTkButton(
            frame_btns, text="🖥️ Pantalla completa\n(traducir una vez)",
            command=self.trad_pantalla_unica, width=120, height=48
        ).pack(side="left", padx=4, pady=4)

        self.btn_continuo_area = ctk.CTkButton(
            frame_btns, text="🔄 Área continua\n(seleccionar)",
            command=self.trad_continuo_area, width=120, height=48,
            fg_color="#1f6aa5"
        )
        self.btn_continuo_area.pack(side="left", padx=4, pady=4)

        self.btn_continuo_full = ctk.CTkButton(
            frame_btns, text="🔄 Pantalla\ncontinua",
            command=self.trad_continuo_full, width=100, height=48,
            fg_color="#1f6aa5"
        )
        self.btn_continuo_full.pack(side="left", padx=4, pady=4)

        self.btn_detener_trad = ctk.CTkButton(
            self, text="⏹ Detener Traducción",
            command=self.detener_traduccion,
            fg_color="gray40", state="disabled"
        )
        self.btn_detener_trad.pack(pady=3)

        # ===== CRÉDITOS =====
        def abrir_twitch():
            webbrowser.open("https://www.twitch.tv/manuel0084")

        creditos = ctk.CTkLabel(
            self,
            text="Créditos: Manuel0084 | twitch.tv/manuel0084",
            font=("Arial", 12), cursor="hand2"
        )
        creditos.pack(pady=10)
        creditos.bind("<Button-1>", lambda e: abrir_twitch())

        # ===== PTT F9 =====
        self.ptt = None
        if PTTManager is not None:
            try:
                self.ptt = PTTManager(
                    app=self,
                    ask_groq=ask_groq,
                    speak=speak,
                    stop_audio=stop_audio,
                    config=config,
                    get_devices=self.get_devices,
                    current_prompt=lambda: self.current_prompt,
                    key="f9",
                    voice="es-MX-DaliaNeural",
                )
                self.log("⌨️ PTT listo - manten F9 para hablar")
            except Exception as e:
                self.log(f"⚠️ PTT no se pudo iniciar: {e}")
                traceback.print_exc()
        else:
            self.log("⚠️ PTT no disponible. Instala: pip install keyboard")

        if GameWatcher is None:
            self.log("⚠️ GameWatcher no disponible. Instala: pip install pillow")
        if TranslatorManager is None:
            self.log("⚠️ Traductor no disponible. Instala: pip install pillow")

    # ==================================================================
    #  MÉTODOS GENERALES
    # ==================================================================
    def log(self, text):
        self.logs.insert("end", text + "\n")
        self.logs.see("end")

    def test_log(self):
        self.log("✅ GUI funcionando")

    def test_voice(self):
        stop_audio()
        _, ia_dev = self.get_devices()
        speak("Hola, prueba de voz", "es-ES-AlvaroNeural", ia_dev)

    def test_ia(self):
        def run():
            stop_audio()
            respuesta = ask_groq("Di algo como VTuber", config.get("GROQ_API_KEY", ""), self.current_prompt)
            self.log(f"IA: {respuesta}")
            _, ia_dev = self.get_devices()
            speak(respuesta, "es-MX-DaliaNeural", ia_dev)
        threading.Thread(target=run, daemon=True).start()

    def ptt_click(self):
        def run():
            from stt import listen
            stop_audio()
            self.log("🎤 Escuchando...")
            text = listen()
            if not text:
                self.log("❌ No se entendio")
                return
            self.log(f"🗣️ Tu: {text}")
            respuesta = ask_groq(text, config.get("GROQ_API_KEY", ""), self.current_prompt)
            self.log(f"🤖 IA: {respuesta}")
            _, ia_dev = self.get_devices()
            speak(respuesta, "es-MX-DaliaNeural", ia_dev)
        threading.Thread(target=run, daemon=True).start()

    def get_devices(self):
        speaker_name = self.speaker_select.get()
        ia_name      = self.ia_select.get()
        monitor_name = self.monitor_select.get() if hasattr(self, "monitor_select") else "(Ninguno)"

        speaker_id = next((i for name, i in self.devices if name == speaker_name), 0)
        ia_id      = next((i for name, i in self.devices if name == ia_name), 0)

        if monitor_name == "(Ninguno)":
            ia_devs = ia_id
        else:
            monitor_id = next((i for name, i in self.devices if name == monitor_name), None)
            if monitor_id is not None and monitor_id != ia_id:
                ia_devs = [ia_id, monitor_id]
            else:
                ia_devs = ia_id

        return speaker_id, ia_devs

    def change_mode(self, filename):
        path = os.path.join(self.promt_folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            self.current_prompt = f.read()
        self.log(f"🎭 Prompt cargado: {filename}")

    def connect_twitch(self):
        def run():
            token   = config.get("TWITCH_TOKEN", "")
            nick    = config.get("NICK", "")
            channel = config.get("CHANNEL", "")
            api_key = config.get("GROQ_API_KEY", "")
            if not token:
                self.log("❌ Falta TWITCH_TOKEN")
                return
            self.log("🔌 Conectando a Twitch...")
            speaker_dev, ia_dev = self.get_devices()
            start_chat(self, token, nick, channel, api_key, speaker_dev, ia_dev, self)
        threading.Thread(target=run, daemon=True).start()

    # ==================================================================
    #  GAME WATCHER
    # ==================================================================
    def toggle_watcher(self):
        if self.game_watcher and self.game_watcher.activo:
            self.game_watcher.detener()
            self.btn_watcher.configure(text="▶ Iniciar Comentarista", fg_color="green")
            self.log("🎮 Comentarista detenido")
        else:
            if GameWatcher is None:
                self.log("❌ game_watcher.py no encontrado o falta instalar pillow")
                return
            try:
                intervalo = int(self.intervalo_var.get())
            except ValueError:
                intervalo = 30

            self.game_watcher = GameWatcher(
                api_key=config.get("GROQ_API_KEY", ""),
                speak_fn=speak,
                stop_audio_fn=stop_audio,
                get_devices_fn=self.get_devices,
                current_prompt_fn=lambda: self.current_prompt,
                intervalo=intervalo,
                voice="es-MX-DaliaNeural",
                log_fn=self.log,
            )
            self.game_watcher.iniciar()
            self.btn_watcher.configure(text="⏹ Detener Comentarista", fg_color="red")
            self.log(f"🎮 Comentarista iniciado (cada {intervalo}s)")

    # ==================================================================
    #  TRADUCTOR
    # ==================================================================
    def _get_translator(self) -> "TranslatorManager | None":
        """Crea el TranslatorManager si no existe todavía."""
        if TranslatorManager is None:
            self.log("❌ Traductor no disponible. Instala: pip install pillow")
            return None
        if self.translator is None:
            try:
                intervalo = int(self.trad_intervalo_var.get())
            except ValueError:
                intervalo = 4
            self.translator = TranslatorManager(
                master=self,
                api_key=config.get("GROQ_API_KEY", ""),
                speak_fn=speak,
                stop_audio_fn=stop_audio,
                get_devices_fn=self.get_devices,
                voice="es-MX-DaliaNeural",
                idioma_destino=self.idioma_var.get(),
                log_fn=self.log,
                leer_en_voz=self.leer_voz_var.get(),
            )
            self.translator.intervalo = intervalo
        else:
            # Actualizar preferencias en caliente
            self.translator.idioma_destino = self.idioma_var.get()
            self.translator.leer_en_voz    = self.leer_voz_var.get()
            try:
                self.translator.intervalo = int(self.trad_intervalo_var.get())
            except ValueError:
                pass
        return self.translator

    def trad_area_unica(self):
        """Selecciona área y traduce una sola vez."""
        t = self._get_translator()
        if t:
            self.log("📐 Dibuja el área a traducir...")
            t.seleccionar_area_y_traducir()

    def trad_pantalla_unica(self):
        """Captura pantalla completa y traduce una sola vez."""
        t = self._get_translator()
        if t:
            self.log("🖥️ Traduciendo pantalla completa...")
            t.traducir_ahora(bbox=None)

    def trad_continuo_area(self):
        """Selecciona área y activa traducción continua."""
        t = self._get_translator()
        if t:
            if t.activo:
                self.log("⚠️ Ya hay una traducción continua activa. Detenla primero.")
                return
            self.log("📐 Dibuja el área para traducción continua...")
            t.seleccionar_area_continuo()
            self.btn_detener_trad.configure(state="normal")
            self.btn_continuo_area.configure(fg_color="orange")
            self.btn_continuo_full.configure(fg_color="orange")

    def trad_continuo_full(self):
        """Pantalla completa en modo continuo."""
        t = self._get_translator()
        if t:
            if t.activo:
                self.log("⚠️ Ya hay una traducción continua activa. Detenla primero.")
                return
            t.area_fija = None
            t.iniciar_continuo()
            self.btn_detener_trad.configure(state="normal")
            self.btn_continuo_area.configure(fg_color="orange")
            self.btn_continuo_full.configure(fg_color="orange")

    def detener_traduccion(self):
        if self.translator:
            self.translator.detener_continuo()
        self.btn_detener_trad.configure(state="disabled")
        self.btn_continuo_area.configure(fg_color="#1f6aa5")
        self.btn_continuo_full.configure(fg_color="#1f6aa5")


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print("\n========== ERROR AL INICIAR ==========")
        traceback.print_exc()
        print("======================================")
        input("\nPresiona ENTER para cerrar...")
