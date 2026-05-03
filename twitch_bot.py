import asyncio
import threading
import random
from twitchio.ext import commands

from audio import speak
from ia import ask_groq
from memory import load_memory, save_memory, add_message, get_context, update_mood


def start_chat(app, token, nick, channel, api_key, speaker_dev, ia_dev, gui_app):

    def run():
        try:
            # 🔥 FIX PYTHON 3.14
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            memory = load_memory()

            class Bot(commands.Bot):

                def __init__(self):
                    super().__init__(
                        token=token,
                        prefix="!",
                        initial_channels=[channel]
                    )

                async def event_ready(self):
                    app.log(f"✅ Conectado como {nick}")

                async def event_message(self, message):
                    if message.echo:
                        return

                    user = message.author.name
                    content = message.content

                    # ===== BOT SPEAKER =====
                    if content.startswith("!sp "):
                        text = content[4:]
                        speak(f"{user} dice {text}", "es-ES-AlvaroNeural", speaker_dev)

                    elif content.startswith("!spm "):
                        text = content[5:]
                        speak(f"{user} dice {text}", "es-MX-DaliaNeural", speaker_dev)

                    # ===== IA =====
                    elif content.startswith("!IA "):
                        try:
                            text = content[4:]
                            app.log(f"💬 {user}: {text}")

                            # 🔥 asegurar que el usuario exista en memoria
                            if user not in memory:
                                add_message(memory, user, "")

                            # 💖 actualizar emoción
                            update_mood(memory, user, text)
                            app.log("DEBUG: mood actualizado")

                            # 🧠 contexto
                            contexto = get_context(memory, user)
                            app.log("DEBUG: contexto listo")

                            prompt_final = f"{gui_app.current_prompt}\n\n{contexto}"

                            # 🤖 IA
                            app.log("DEBUG: llamando IA...")
                            respuesta = ask_groq(text, api_key, prompt_final)
                            app.log(f"DEBUG: respuesta IA = {respuesta}")

                            if not respuesta:
                                respuesta = "No pude responder eso..."

                            # 🎭 frases VTuber
                            frases = ["Te respondo", "Te contesto", "Te digo", "Sabes"]
                            inicio = random.choice(frases)

                            mood = memory[user].get("mood", 0)

                            if mood >= 3:
                                mensaje_final = f"{inicio} {user}~ 💖 {respuesta}"
                                voz = "es-MX-DaliaNeural"
                            elif mood <= -3:
                                mensaje_final = f"{inicio} {user}... hm. {respuesta}"
                                voz = "es-ES-AlvaroNeural"
                            else:
                                mensaje_final = f"{inicio} {user}... {respuesta}"
                                voz = "es-MX-DaliaNeural"

                            app.log(f"🤖 IA: {mensaje_final}")

                            # 💾 memoria
                            add_message(memory, user, text)
                            add_message(memory, user, respuesta)
                            save_memory(memory)

                            # 🔊 voz
                            app.log("DEBUG: enviando a voz...")
                            speak(mensaje_final, voz, ia_dev)

                        except Exception as e:
                            import traceback
                            app.log("❌ ERROR IA:")
                            app.log(traceback.format_exc())

            bot = Bot()

            loop.run_until_complete(bot.start())

        except Exception as e:
            app.log(f"❌ Error Twitch: {e}")

    threading.Thread(target=run, daemon=True).start()