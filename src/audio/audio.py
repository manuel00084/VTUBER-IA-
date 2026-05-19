import threading
import queue
import asyncio
import edge_tts
import tempfile
import os

import numpy as np
import sounddevice as sd
import soundfile as sf

audio_queue = queue.Queue()

# Cache de samplerates para evitar sd.query_devices() repetido
_samplerate_cache = {}


def get_device_samplerate(device):
    if device in _samplerate_cache:
        return _samplerate_cache[device]
    try:
        info = sd.query_devices(device, 'output')
        rate = int(info['default_samplerate'])
        _samplerate_cache[device] = rate
        return rate
    except Exception:
        return 48000


async def _generar_tts(text, voice, path):
    emocion = detectar_emocion(text)
    rate, pitch = "+0%", "+0Hz"
    if emocion == "feliz":
        rate, pitch = "+15%", "+6Hz"
    elif emocion == "enojado":
        rate, pitch = "-5%", "-4Hz"
    elif emocion == "sorpresa":
        rate, pitch = "+10%", "+8Hz"
    elif emocion == "triste":
        rate, pitch = "-10%", "-2Hz"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(path)


# ===== DETECCION DE EMOCION =====
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


def resample_audio(data, src_rate, dst_rate):
    if src_rate == dst_rate:
        return data
    from scipy import signal
    n_out = int(round(len(data) * dst_rate / src_rate))
    if data.ndim == 1:
        return signal.resample(data, n_out).astype(np.float32)
    out = np.zeros((n_out, data.shape[1]), dtype=np.float32)
    for ch in range(data.shape[1]):
        out[:, ch] = signal.resample(data[:, ch], n_out).astype(np.float32)
    return out


def _play_on_device(data, src_fs, device, volume=1.0):
    """Reproduce audio en un dispositivo (con remuestreo si hace falta)."""
    try:
        d = data.copy()
        # 1) Normalizar a 85% para dejar margen de amplificación
        peak = np.max(np.abs(d))
        if peak > 0:
            d = d * (0.85 / peak)
        # 2) Aplicar ganancia de volumen
        d = d * volume
        dev_rate = get_device_samplerate(device)
        d = resample_audio(d, src_fs, dev_rate) if src_fs != dev_rate else d
        # Forzar mono si el audio tiene mas de 1 canal
        if d.ndim > 1 and d.shape[1] > 1:
            d = np.mean(d, axis=1)
        # 3) Clip protection final
        max_val = np.max(np.abs(d))
        if max_val > 0.99:
            d = d * (0.99 / max_val)
        try:
            sd.play(d, dev_rate, device=device, blocking=True)
        except Exception as e1:
            print(f"WARNING Retrying device {device} at 48000Hz: {e1}")
            d2 = data.copy()
            peak2 = np.max(np.abs(d2))
            if peak2 > 0:
                d2 = d2 * (0.6 / peak2) * volume
            d2 = resample_audio(d2, src_fs, 48000)
            if d2.ndim > 1 and d2.shape[1] > 1:
                d2 = np.mean(d2, axis=1)
            max_val2 = np.max(np.abs(d2))
            if max_val2 > 0.99:
                d2 = d2 * (0.99 / max_val2)
            sd.play(d2, 48000, device=device, blocking=True)
    except Exception as e:
        print(f"ERROR playing in device {device}: {e}")


# ===== WORKER =====
def audio_worker():
    while True:
        try:
            text, voice, devices, volume = audio_queue.get()

            # normaliza: puede llegar un int o una lista
            if isinstance(devices, (list, tuple)):
                dev_list = list(devices)
            else:
                dev_list = [devices]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                path = f.name

            try:
                asyncio.run(_generar_tts(text, voice, path))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(_generar_tts(text, voice, path))
                loop.close()

            try:
                data, fs = sf.read(path, dtype='float32')
                
                import threading
                threads = []
                for dev in dev_list:
                    if dev is None or dev == -1:
                        continue
                    t = threading.Thread(target=_play_on_device, args=(data, fs, dev, volume), daemon=True)
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()
            except Exception as e:
                print("ERROR playing audio:", e)

            try:
                os.remove(path)
            except Exception:
                pass

        except Exception as e:
            print("ERROR Worker error:", e)


def stop_audio():
    try:
        sd.stop()
    except Exception:
        pass


def speak(text, voice="es-ES-AlvaroNeural", device=2, volume=1.0):
    """device puede ser int (un dispositivo) o lista [dev1, dev2, ...]."""
    try:
        audio_queue.put((text, voice, device, volume))
    except Exception as e:
        print("ERROR speak:", e)


def play_file(path, device=2):
    """Reproduce un archivo de audio (MP3/WAV/OGG) directamente"""
    if not path or not os.path.isfile(path):
        print(f"ERROR play_file: archivo no encontrado: {path}")
        return
    try:
        data, fs = sf.read(path, dtype='float32')
    except Exception as e:
        print(f"ERROR play_file sf.read: {e}")
        try:
            import subprocess
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", path],
                check=True
            )
            return
        except Exception as e2:
            print(f"ERROR play_file ffplay fallback: {e2}")
            return
    _play_on_device(data, fs, device)