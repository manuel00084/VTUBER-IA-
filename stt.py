import sounddevice as sd
import queue
import sys
import json
import vosk
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "vosk-model-small-es-0.42")

q = queue.Queue()
stream = None
recognizer = None
_model = None


def _callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))


def _get_model():
    global _model
    if _model is None:
        _model = vosk.Model(MODEL_PATH)
    return _model


def listen():
    try:
        rec = vosk.KaldiRecognizer(_get_model(), 16000)
        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                               channels=1, callback=_callback):
            print("🎤 Escuchando...")
            while True:
                data = q.get()
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    return result.get("text", "")
    except Exception as e:
        print("❌ STT error:", e)
        return None


def listen_stream_start():
    global stream, recognizer
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break
    recognizer = vosk.KaldiRecognizer(_get_model(), 16000)
    stream = sd.RawInputStream(
        samplerate=16000, blocksize=8000, dtype='int16',
        channels=1, callback=_callback
    )
    stream.start()


def listen_stream_stop():
    global stream, recognizer
    text_parts = []
    try:
        if stream is not None:
            stream.stop()
            stream.close()
        while not q.empty():
            data = q.get()
            if recognizer.AcceptWaveform(data):
                res = json.loads(recognizer.Result())
                if res.get("text"):
                    text_parts.append(res["text"])
        final = json.loads(recognizer.FinalResult())
        if final.get("text"):
            text_parts.append(final["text"])
        return " ".join(text_parts).strip()
    except Exception as e:
        print("❌ STT stream error:", e)
        return None
    finally:
        stream = None
        recognizer = None