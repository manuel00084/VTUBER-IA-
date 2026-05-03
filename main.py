import customtkinter as ctk
import threading
import os
import traceback

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

config = load_config()


# ===== APP =====
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VTuber AI - ESTABLE")
        self.geometry("520x650")

        # ===== AUDIO THREAD =====
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

        self.logs = ctk.CTkTextbox(self, height=250)
        self.logs.pack(pady=10)

        # ===== BOTONES =====
        ctk.CTkButton(self, text="Test GUI", command=self.test_log).pack(pady=5)
        ctk.CTkButton(self, text="Test Voz", command=self.test_voice).pack(pady=5)
        ctk.CTkButton(self, text="Test IA", command=self.test_ia).pack(pady=5)
        ctk.CTkButton(self, text="Conectar Twitch", command=self.connect_twitch).pack(pady=10)

        # 🎤 BOTÓN ESTABLE
        ctk.CTkButton(self, text="🎤 Hablar con IA", command=self.ptt_click).pack(pady=5)

        # ===== DISPOSITIVOS =====
        self.devices = get_output_devices()
        device_names = [name for name, i in self.devices]

        ctk.CTkLabel(self, text="🔊 Bot Speaker").pack(pady=5)
        self.speaker_select = ctk.CTkComboBox(self, values=device_names)
        self.speaker_select.pack(pady=5)

        ctk.CTkLabel(self, text="🤖 IA Voz").pack(pady=5)
        self.ia_select = ctk.CTkComboBox(self, values=device_names)
        self.ia_select.pack(pady=5)

        if device_names:
            self.speaker_select.set(device_names[0])
            self.ia_select.set(device_names[0])

        # ===== PROMPT =====
        ctk.CTkLabel(self, text="🎭 Prompt IA").pack(pady=5)

        self.mode_select = ctk.CTkComboBox(
            self,
            values=self.promt_files,
            command=self.change_mode
        )
        self.mode_select.pack(pady=5)

        self.mode_select.set(self.promt_files[0])
        self.change_mode(self.promt_files[0])

    # ===== LOG =====
    def log(self, text):
        self.logs.insert("end", text + "\n")
        self.logs.see("end")

    # ===== TESTS =====
    def test_log(self):
        self.log("✅ GUI funcionando")

    def test_voice(self):
        stop_audio()
        speak("Hola, prueba de voz", "es-ES-AlvaroNeural", None)

    def test_ia(self):
        def run():
            stop_audio()
            respuesta = ask_groq("Di algo como VTuber", config.get("GROQ_API_KEY", ""), self.current_prompt)
            self.log(f"IA: {respuesta}")
            _, ia_dev = self.get_devices()
            speak(respuesta, "es-MX-DaliaNeural", ia_dev)

        threading.Thread(target=run, daemon=True).start()

    # ===== PTT SIMPLE =====
    def ptt_click(self):
        def run():
            from stt import listen

            stop_audio()
            self.log("🎤 Escuchando...")

            text = listen()

            if not text:
                self.log("❌ No se entendió")
                return

            self.log(f"🗣️ Tú: {text}")

            respuesta = ask_groq(
                text,
                config.get("GROQ_API_KEY", ""),
                self.current_prompt
            )

            self.log(f"🤖 IA: {respuesta}")

            _, ia_dev = self.get_devices()
            speak(respuesta, "es-MX-DaliaNeural", ia_dev)

        threading.Thread(target=run, daemon=True).start()

    def get_devices(self):
        speaker_name = self.speaker_select.get()
        ia_name = self.ia_select.get()

        speaker_id = next((i for name, i in self.devices if name == speaker_name), 0)
        ia_id = next((i for name, i in self.devices if name == ia_name), 0)

        return speaker_id, ia_id

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


# ===== RUN =====
if __name__ == "__main__":
    app = App()
    app.mainloop()