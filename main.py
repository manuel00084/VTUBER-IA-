import customtkinter as ctk
import threading
import os
import traceback
import webbrowser  # <-- agregado

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

config = load_config()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VTuber AI - ESTABLE")
        self.geometry("520x760")

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
        ctk.CTkLabel(self, text="Sistema iniciado (modo estable)").pack(pady=10)

        self.logs = ctk.CTkTextbox(self, height=220)
        self.logs.pack(pady=10)

        ctk.CTkButton(self, text="Test GUI", command=self.test_log).pack(pady=3)
        ctk.CTkButton(self, text="Test Voz", command=self.test_voice).pack(pady=3)
        ctk.CTkButton(self, text="Test IA", command=self.test_ia).pack(pady=3)
        ctk.CTkButton(self, text="Conectar Twitch", command=self.connect_twitch).pack(pady=8)
        ctk.CTkButton(self, text="🎤 Hablar con IA", command=self.ptt_click).pack(pady=3)

        # ===== DISPOSITIVOS =====
        self.devices = get_output_devices()
        device_names = [name for name, i in self.devices]

        ctk.CTkLabel(self, text="🔊 Bot Speaker").pack(pady=3)
        self.speaker_select = ctk.CTkComboBox(self, values=device_names)
        self.speaker_select.pack(pady=3)

        ctk.CTkLabel(self, text="🤖 IA Voz (cable virtual / VMagic)").pack(pady=3)
        self.ia_select = ctk.CTkComboBox(self, values=device_names)
        self.ia_select.pack(pady=3)

        ctk.CTkLabel(self, text="🎧 Monitor (tus auriculares)").pack(pady=3)
        self.monitor_select = ctk.CTkComboBox(self, values=["(Ninguno)"] + device_names)
        self.monitor_select.pack(pady=3)
        self.monitor_select.set("(Ninguno)")

        if device_names:
            self.speaker_select.set(device_names[0])
            self.ia_select.set(device_names[0])

        # ===== PROMPT =====
        ctk.CTkLabel(self, text="🎭 Prompt IA").pack(pady=3)
        self.mode_select = ctk.CTkComboBox(self, values=self.promt_files, command=self.change_mode)
        self.mode_select.pack(pady=3)
        self.mode_select.set(self.promt_files[0])
        self.change_mode(self.promt_files[0])

        # ===== CRÉDITOS (AGREGADO) =====
        def abrir_twitch():
            webbrowser.open("https://www.twitch.tv/manuel0084")

        creditos = ctk.CTkLabel(
            self,
            text="Créditos: Manuel0084 | twitch.tv/manuel0084",
            font=("Arial", 12),
            cursor="hand2"
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
                self.log("⌨️ PTT listo - manten F9 para hablar (funciona minimizado)")
            except Exception as e:
                self.log(f"⚠️ PTT no se pudo iniciar: {e}")
                traceback.print_exc()
        else:
            self.log("⚠️ PTT no disponible. Instala: pip install keyboard")

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
        ia_name = self.ia_select.get()
        monitor_name = self.monitor_select.get() if hasattr(self, "monitor_select") else "(Ninguno)"

        speaker_id = next((i for name, i in self.devices if name == speaker_name), 0)
        ia_id = next((i for name, i in self.devices if name == ia_name), 0)

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
            token = config.get("TWITCH_TOKEN", "")
            nick = config.get("NICK", "")
            channel = config.get("CHANNEL", "")
            api_key = config.get("GROQ_API_KEY", "")
            if not token:
                self.log("❌ Falta TWITCH_TOKEN")
                return
            self.log("🔌 Conectando a Twitch...")
            speaker_dev, ia_dev = self.get_devices()
            start_chat(self, token, nick, channel, api_key, speaker_dev, ia_dev, self)
        threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print("\n========== ERROR AL INICIAR ==========")
        traceback.print_exc()
        print("======================================")
        input("\nPresiona ENTER para cerrar...")