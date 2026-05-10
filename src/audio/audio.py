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
                _play_multi(data, fs, dev_list)
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


def speak_fish_audio(text, voice, device=0):
    """Generate TTS using Fish Audio API"""
    try:
        from src.core.config import load_config
        config_dict = load_config()
        api_key = config_dict.get("FISH_API_KEY", "")
        
        if not api_key:
            print("ERROR Fish Audio API Key not configured")
            return False
            
        url = "https://api.fish.audio/v1/tts"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "model": "suno"
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"ERROR Fish Audio API error: {response.status_code} - {response.text}")
            return False
        
        # Save audio to temp file and play it
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(response.content)
            temp_path = f.name
            
            try:
                data, fs = sf.read(temp_path, dtype='float32')
                _play_multi(data, fs, [device] if isinstance(device, int) else device)
            except Exception as e:
                print(f"ERROR playing Fish Audio: {e}")
            finally:
                try:
                    os.remove(temp_path)
                except:
                    pass
        
        return True
        
    except Exception as e:
        print(f"ERROR in Fish Audio TTS: {e}")
        return False


def speak(text, voice="es-ES-AlvaroNeural", device=0):
    """device puede ser int (un dispositivo) o lista [dev1, dev2, ...]."""
    try:
        if voice.startswith("fish_"):
            success = speak_fish_audio(text, voice, device)
            if not success:
                audio_queue.put((text, "es-ES-AlvaroNeural", device))
        else:
            audio_queue.put((text, voice, device))
    except Exception as e:
        print("ERROR speak:", e)