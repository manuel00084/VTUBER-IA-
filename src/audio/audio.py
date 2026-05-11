import threading
import queue
import asyncio
import edge_tts
import tempfile
import os
import requests
import json

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import butter, lfilter

from src.core.config import load_config

audio_queue = queue.Queue()


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


# ===== EQUALIZADOR =====
def _apply_eq(data, fs, bass_db, treble_db, autotune_amount=0):
    """
    Aplicar ecualización de graves, agudos y Auto-Tune.
    bass_db: -12 a +12 dB
    treble_db: -12 a +12 dB
    autotune_amount: 0-100 (intensidad del efecto)
    """
    try:
        from scipy.signal import butter, lfilter
        
        nyq = fs / 2
        
        # Filtro graves (low shelf) - frecuencia de corte ~200Hz
        if bass_db != 0:
            fc_bass = min(200, nyq - 1)
            # Convertir dB a ganancia lineal
            gain_bass = 10 ** (bass_db / 20.0)
            # Filtro paso bajo simple para graves
            b, a = butter(2, fc_bass / nyq, btype='low')
            data_low = lfilter(b, a, data)
            # Mezclar señal original + graves procesados
            data = data + (data_low - data) * (gain_bass - 1)
        
        # Filtro agudos (high shelf) - frecuencia de corte ~2000Hz
        if treble_db != 0:
            fc_treble = min(2000, nyq - 1)
            gain_treble = 10 ** (treble_db / 20.0)
            # Aplicar filtro paso alto
            b, a = butter(2, fc_treble / nyq, btype='high')
            data_high = lfilter(b, a, data)
            # Mezclar
            data = data + (data_high - data) * (gain_treble - 1)
        
        # Auto-Tune: corrige tono基本的
        if autotune_amount > 0:
            data = _apply_autotune(data, fs, autotune_amount)
        
        # Normalizar para evitar clipping
        max_val = np.max(np.abs(data))
        if max_val > 0.95:
            data = data * (0.95 / max_val)
        
        return data
    except Exception as e:
        print("Error applying EQ:", e)
        return data


def _apply_autotune(data, fs, amount):
    """
    Auto-Tune simple: suaviza el tono de la voz.
    amount: 0-100 (intensidad)
    """
    try:
        # Factor de suavizado según amount
        alpha = amount / 200.0  # 0 a 0.5
        
        # Aplicar filtro de suavizado (low-pass simple)
        result = np.zeros_like(data)
        result[0] = data[0]
        
        for i in range(1, len(data)):
            result[i] = alpha * result[i-1] + (1 - alpha) * data[i]
        
        return result
    except Exception as e:
        print("Error Auto-Tune:", e)
        return data


def resample_audio(data, src_rate, dst_rate):
    if src_rate == dst_rate:
        return data
    ratio = dst_rate / src_rate
    if data.ndim == 1:
        n_out = int(round(len(data) * ratio))
        x_old = np.linspace(0, 1, len(data), endpoint=False)
        x_new = np.linspace(0, 1, n_out, endpoint=False)
        return np.interp(x_new, x_old, data).astype(np.float32)
    else:
        n_out = int(round(data.shape[0] * ratio))
        x_old = np.linspace(0, 1, data.shape[0], endpoint=False)
        x_new = np.linspace(0, 1, n_out, endpoint=False)
        out = np.zeros((n_out, data.shape[1]), dtype=np.float32)
        for ch in range(data.shape[1]):
            out[:, ch] = np.interp(x_new, x_old, data[:, ch])
        return out


def get_device_samplerate(device):
    try:
        info = sd.query_devices(device, 'output')
        return int(info['default_samplerate'])
    except Exception:
        return 48000


def _play_on_device(data, src_fs, device):
    """Reproduce audio en un dispositivo (con remuestreo si hace falta)."""
    try:
        dev_rate = get_device_samplerate(device)
        d = resample_audio(data, src_fs, dev_rate) if src_fs != dev_rate else data
        try:
            sd.play(d, dev_rate, device=device, blocking=True)
        except Exception as e1:
            print(f"WARNING Retrying device {device} at 48000Hz: {e1}")
            d2 = resample_audio(data, src_fs, 48000)
            sd.play(d2, 48000, device=device, blocking=True)
    except Exception as e:
        print(f"ERROR playing in device {device}: {e}")


def _play_multi(data, fs, devices):
    """Reproduce el mismo audio en varios dispositivos en paralelo."""
    devs = [d for d in devices if d is not None and d != -1]
    if not devs:
        return
    threads = []
    for dev in devs:
        t = threading.Thread(target=_play_on_device, args=(data, fs, dev), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


# ===== WORKER =====
def audio_worker():
    while True:
        try:
            text, voice, devices = audio_queue.get()

            # normaliza: puede llegar un int o una lista
            if isinstance(devices, (list, tuple)):
                dev_list = list(devices)
            else:
                dev_list = [devices]

            async def generar_tts(path):
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
                
                # Aplicar EQ manual desde config
                cfg = load_config()
                eq_speed = cfg.get("EQ_SPEED", 0)
                
                # Ajustar velocidad
                if eq_speed != 0:
                    rate = f"{'+' if eq_speed > 0 else ''}{int(eq_speed)}%"
                
                communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
                await communicate.save(path)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                path = f.name

            try:
                asyncio.run(generar_tts(path))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(generar_tts(path))
                loop.close()

            try:
                data, fs = sf.read(path, dtype='float32')
                
                # Obtener IDs de dispositivos
                cfg = load_config()
                sp_idx = int(cfg.get("SPEAKER_DEVICE", 0))
                ia_idx = int(cfg.get("IA_DEVICE", 0))
                mn_idx = int(cfg.get("MONITOR_DEVICE", 0))
                
                # EQ settings
                eq_bass = cfg.get("EQ_BASS", 0)
                eq_treble = cfg.get("EQ_TREBLE", 0)
                eq_autotune = cfg.get("EQ_AUTOTUNE", 0)
                apply_eq = eq_bass != 0 or eq_treble != 0 or eq_autotune != 0
                
                # Reproducir en cada dispositivo por separado
                for dev in dev_list:
                    if dev is None or dev == -1:
                        continue
                    if dev == mn_idx and apply_eq:
                        # Solo Monitor recibe EQ
                        data_dev = _apply_eq(data.copy(), fs, eq_bass, eq_treble, eq_autotune)
                    else:
                        # Bot Speaker e IA Voz sin EQ
                        data_dev = data
                    _play_on_device(data_dev, fs, dev)
            except Exception as e:
                print("ERROR playing audio:", e)

            try:
                os.remove(path)
            except:
                pass

        except Exception as e:
            print("ERROR Worker error:", e)


def stop_audio():
    try:
        sd.stop()
    except:
        pass


def speak(text, voice="es-ES-AlvaroNeural", device=0):
    """device puede ser int (un dispositivo) o lista [dev1, dev2, ...]."""
    try:
        audio_queue.put((text, voice, device))
    except Exception as e:
        print("ERROR speak:", e)