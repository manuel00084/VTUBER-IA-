import asyncio
import threading
import random
from twitchio.ext import commands
from audio import speak, stop_audio
from ia import ask_groq
from memory import load_memory, save_memory, add_message, get_context, update_mood


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

            memory = load_memory()

            class Bot(commands.Bot):
                def __init__(self):
                    # El token puede venir con o sin "oauth:" — lo normalizamos
                    tok = token.strip()
                    if not tok.startswith("oauth:"):
                        tok = f"oauth:{tok}"
                    super().__init__(
                        token=tok,
                        prefix="!",
                        initial_channels=[channel.strip().lstrip("#")]
                    )

                # ── Eventos ──────────────────────────────────────────────
                async def event_ready(self):
                    app.log(f"✅ Bot conectado como {self.nick} en #{channel}")

                async def event_message(self, message):
                    if message.echo:
                        return

                    user    = message.author.name.lower()
                    content = message.content.strip()

                    # Delegar a comandos de twitchio
                    await self.handle_commands(message)

                    # ── BOT SPEAKER ───────────────────────────────────────
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

                    # ── BOT IA ────────────────────────────────────────────
                    elif content.lower().startswith("!ia "):
                        texto = content[4:].strip()
                        if not texto:
                            return
                        # Procesar en hilo para no bloquear el evento de Twitch
                        threading.Thread(
                            target=_procesar_ia,
                            args=(user, texto, memory, api_key, gui_app,
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


# ── Procesamiento IA en hilo separado ────────────────────────────────────────
def _procesar_ia(user, texto, memory, api_key, gui_app, ia_dev, app):
    """
    Llama a Groq, construye la respuesta con personalidad y la vocaliza.
    Se ejecuta en un hilo para no bloquear el loop de Twitch.
    """
    try:
        app.log(f"💬 {user}: {texto}")

        # Inicializar usuario en memoria si no existe
        if user not in memory:
            memory[user] = {"messages": [], "mood": 0}

        # Actualizar estado emocional basado en el mensaje
        try:
            update_mood(memory, user, texto)
        except Exception:
            pass   # si falla el mood no es crítico

        # Construir contexto conversacional
        try:
            contexto = get_context(memory, user)
        except Exception:
            contexto = ""

        prompt_final = f"{gui_app.current_prompt}\n\n{contexto}".strip()

        # Llamar a la IA
        respuesta = ask_groq(texto, api_key, prompt_final)

        if not respuesta or respuesta.strip() == "":
            respuesta = "Hmm, no sé qué decirte ahora mismo..."

        # Personalizar según estado emocional
        mood = memory[user].get("mood", 0)
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

        # Guardar en memoria
        try:
            add_message(memory, user, texto)
            add_message(memory, user, respuesta)
            save_memory(memory)
        except Exception:
            pass   # fallo de memoria no es crítico

        # Vocalizar (detiene audio anterior primero)
        stop_audio()
        speak(mensaje_final, voz, ia_dev)

    except Exception as e:
        import traceback
        app.log(f"❌ Error procesando IA para {user}: {e}")
        app.log(traceback.format_exc())
