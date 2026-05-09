import asyncio
import threading
import random

from twitchio.ext import commands
from src.audio import speak, stop_audio
from src.ai import ask_ai

from src.ai.memory import (
    load_memory, save_memory, add_message,
    get_context, update_mood
)


def start_chat(app, token, nick, channel, api_key, speaker_dev, ia_dev, gui_app):
    """
    Inicia el bot de Twitch en un hilo separado.

    Comandos del chat:
      !sp <texto>   — Bot speaker voz neutra (hombre)
      !sph <texto>  — Bot speaker voz hombre (igual que !sp)
      !spm <texto>  — Bot speaker voz mujer
      !IA <texto>   — Hablar con la VTuber IA
    """

    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            mem_data = load_memory()

            class Bot(commands.Bot):
                def __init__(self):
                    tok = token.strip()
                    if not tok.startswith("oauth:"):
                        tok = f"oauth:{tok}"
                    super().__init__(
                        token=tok,
                        prefix="!",
                        initial_channels=[channel.strip().lstrip("#")]
                    )

                async def event_ready(self):
                    app.log(f"✅ Bot conectado como {self.nick} en #{channel}")

                async def event_message(self, message):
                    if message.echo:
                        return

                    user    = message.author.name.lower()
                    content = message.content.strip()

                    await self.handle_commands(message)

                    if content.lower().startswith("!sp "):
                        texto = content[4:].strip()
                        if texto:
                            speak(f"{user} dice: {texto}", "es-ES-AlvaroNeural", speaker_dev)

                    elif content.lower().startswith("!sph "):
                        texto = content[5:].strip()
                        if texto:
                            speak(f"{user} dice: {texto}", "es-ES-AlvaroNeural", speaker_dev)

                    elif content.lower().startswith("!spm "):
                        texto = content[5:].strip()
                        if texto:
                            speak(f"{user} dice: {texto}", "es-MX-DaliaNeural", speaker_dev)

                    elif content.lower().startswith("!ia "):
                        texto = content[4:].strip()
                        if not texto:
                            return
                        threading.Thread(
                            target=_procesar_ia,
                            args=(user, texto, mem_data, api_key, gui_app,
                                  ia_dev, app),
                            daemon=True
                        ).start()

                async def event_error(self, error: Exception, data=None):
                    app.log(f"⚠ Error en bot Twitch: {error}")

            bot = Bot()
            loop.run_until_complete(bot.start())

        except Exception as e:
            import traceback
            app.log(f"❌ Error al iniciar Twitch: {e}")
            app.log(traceback.format_exc())

    threading.Thread(target=run, daemon=True).start()


def _procesar_ia(user, texto, mem_data, api_key, gui_app, ia_dev, app):
    try:
        app.log(f"💬 {user}: {texto}")

        if user not in mem_data:
            mem_data[user] = {"history": [], "data": [], "mood": 0}

        try:
            update_mood(mem_data, user, texto)
        except Exception:
            pass

        try:
            contexto = get_context(mem_data, user)
        except Exception:
            contexto = ""

        prompt_final = f"{gui_app.current_prompt}\n\n{contexto}".strip()
        api_key_cerebras = api_key
        try:
            from src.core.config import load_config
            cfg = load_config()
            api_key_cerebras = cfg.get("CEREBRAS_API_KEY", api_key)
        except:
            pass
        respuesta = ask_ai(texto, api_key_cerebras, prompt_final, "cerebras")

        if not respuesta or respuesta.strip() == "":
            respuesta = "Hmm, no sé qué decirte ahora mismo..."

        mood = mem_data[user].get("mood", 0)
        frases = ["Oye", "Mira", "Escucha", "Sabes"]
        inicio = random.choice(frases)

        if mood >= 3:
            mensaje_final = f"{inicio} {user}~ 💖 {respuesta}"
            voz = "es-MX-DaliaNeural"
        elif mood <= -3:
            mensaje_final = f"{inicio} {user}... {respuesta}"
            voz = "es-ES-ElviraNeural"
        else:
            mensaje_final = f"{inicio} {user}... {respuesta}"
            voz = "es-MX-DaliaNeural"

        app.log(f"🤖 IA → {user}: {respuesta}")

        try:
            add_message(mem_data, user, texto)
            add_message(mem_data, user, respuesta)
            save_memory(mem_data)
        except Exception:
            pass

        stop_audio()
        speak(mensaje_final, voz, ia_dev)

    except Exception as e:
        import traceback
        app.log(f"❌ Error procesando IA para {user}: {e}")
        app.log(traceback.format_exc())