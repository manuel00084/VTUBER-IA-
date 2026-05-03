import threading
import traceback

try:
    import keyboard
except Exception as e:
    keyboard = None
    print("No se pudo importar 'keyboard':", e)


class PTTManager:
    """Push-To-Talk global con F9 (hold-to-talk)."""

    def __init__(self, app, ask_groq, speak, stop_audio, config,
                 get_devices, current_prompt, key="f9",
                 voice="es-MX-DaliaNeural"):
        if keyboard is None:
            raise RuntimeError("Libreria 'keyboard' no instalada. Ejecuta: pip install keyboard")

        self.app = app
        self.ask_groq = ask_groq
        self.speak = speak
        self.stop_audio = stop_audio
        self.config = config
        self.get_devices = get_devices
        self.current_prompt = current_prompt
        self.key = key
        self.voice = voice

        self.recording = False
        self._lock = threading.Lock()

        keyboard.on_press_key(self.key, self._on_press, suppress=False)
        keyboard.on_release_key(self.key, self._on_release, suppress=False)

    def _log(self, text):
        try:
            self.app.after(0, lambda: self.app.log(text))
        except Exception:
            print(text)

    def _on_press(self, _event):
        with self._lock:
            if self.recording:
                return
            self.recording = True
        try:
            from stt import listen_stream_start
            self.stop_audio()
            listen_stream_start()
            self._log("Grabando... (suelta F9 para enviar)")
        except Exception as e:
            self.recording = False
            self._log(f"Error iniciando PTT: {e}")
            traceback.print_exc()

    def _on_release(self, _event):
        with self._lock:
            if not self.recording:
                return
            self.recording = False
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        try:
            from stt import listen_stream_stop
            text = listen_stream_stop()
            if not text:
                self._log("No se entendio nada")
                return
            self._log(f"Tu: {text}")
            respuesta = self.ask_groq(text, self.config.get("GROQ_API_KEY", ""), self.current_prompt())
            self._log(f"IA: {respuesta}")
            _, ia_dev = self.get_devices()
            self.speak(respuesta, self.voice, ia_dev)
        except Exception as e:
            self._log(f"PTT error: {e}")
            traceback.print_exc()