import threading
import queue
import asyncio
import edge_tts
import tempfile
import os

import sounddevice as sd
import soundfile as sf

audio_queue = queue.Queue()

# ===== DETECCIÓN DE EMOCIÓN =====
def detectar_emocion(texto):
    t = texto.lower()

    if any(p in t for p in ["jaja", "genial", "feliz", "emocion", "divertido"]):
        return "feliz"
    elif any(p in t for p in ["enojo", "molesto", "odio", "rabia"]):
        return "enojado"
    elif any(p in t for p in ["wow", "sorpresa", "increible", "no puede ser"]):
        return "sorpresa"
    elif any(p in t for p in ["triste", "lo siento", "perdon"]):
        return "triste"

    return "normal"


# ===== WORKER =====
def audio_worker():
    while True:
        try:
            text, voice, device = audio_queue.get()

            # 🔒 función async segura
            async def generar_tts(path):
                emocion = detectar_emocion(text)

                rate = "+0%"
                pitch = "+0Hz"

                if emocion == "feliz":
                    rate = "+15%"
                    pitch = "+6Hz"
                elif emocion == "enojado":
                    rate = "-5%"
                    pitch = "-4Hz"
                elif emocion == "sorpresa":
                    rate = "+10%"
                    pitch = "+8Hz"
                elif emocion == "triste":
                    rate = "-10%"
                    pitch = "-2Hz"

                communicate = edge_tts.Communicate(
                    text=text,
                    voice=voice,
                    rate=rate,
                    pitch=pitch
                )

                await communicate.save(path)

            # 📁 archivo temporal
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                path = f.name

            # ⚙️ ejecutar async
            try:
                asyncio.run(generar_tts(path))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(generar_tts(path))
                loop.close()

            # 🔊 reproducir audio
            try:
                data, fs = sf.read(path, dtype='float32')

                sd.play(data, fs, device=device)
                sd.wait()

            except Exception as e:
                print("❌ Error reproducción:", e)

            # 🧹 limpiar archivo
            try:
                os.remove(path)
            except:
                pass

        except Exception as e:
            print("❌ Worker error:", e)


# ===== STOP AUDIO =====
def stop_audio():
    try:
        sd.stop()
    except:
        pass


# ===== FUNCIÓN PRINCIPAL =====
def speak(text, voice="es-ES-AlvaroNeural", device=0):
    try:
        audio_queue.put((text, voice, device))
    except Exception as e:
        print("❌ Error speak:", e)