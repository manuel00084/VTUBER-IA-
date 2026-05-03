import threading

def start_ptt(app, ask_groq, speak, stop_audio, config, get_devices, current_prompt):
    def run():
        try:
            from stt import listen
        except Exception as e:
            app.log(f"❌ STT error: {e}")
            return

        app.log("🎤 PTT activo (modo simple)")

        while True:
            try:
                stop_audio()
                app.log("🎤 Escuchando...")

                text = listen()

                if not text:
                    app.log("❌ No se entendió")
                    continue

                app.log(f"🗣️ Tú: {text}")

                respuesta = ask_groq(
                    text,
                    config.get("GROQ_API_KEY", ""),
                    current_prompt()
                )

                app.log(f"🤖 IA: {respuesta}")

                _, ia_dev = get_devices()
                speak(respuesta, "es-MX-DaliaNeural", ia_dev)

            except Exception as e:
                app.log(f"❌ Error PTT: {e}")

    threading.Thread(target=run, daemon=True).start()