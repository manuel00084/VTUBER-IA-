import sounddevice as sd
import queue
import sys
import json
import os

VOSK_OK = False
vosk = None
_model = None

MODEL_PATH = os.path.join(os.path.dirname(__file__), "vosk-model-small-es-0.42")

def _try_load_vosk():
    global VOSK_OK, vosk
    try:
        import vosk as v
        vosk = v
        VOSK_OK = True
        return True
    except Exception as e:
        print(f"Vosk not available: {e}")
        return False

def _ensure_vosk():
    global vosk, _model
    if not VOSK_OK:
        _try_load_vosk()
    if VOSK_OK and _model is None and os.path.exists(MODEL_PATH):
        try:
            _model = vosk.Model(MODEL_PATH)
        except Exception as e:
            print(f"Vosk model error: {e}")
            VOSK_OK = False

q = queue.Queue()
stream = None
recognizer = None
_stream_active = False

_try_load_vosk()

def _callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))


def listen():
    global stream, recognizer, _model
    _ensure_vosk()
    if not VOSK_OK:
        print("STT: Vosk not available")
        return ""
    if not os.path.exists(MODEL_PATH):
        print(f"STT: Model not found at {MODEL_PATH}")
        return ""

    try:
        if _model is None:
            if not os.path.exists(MODEL_PATH):
                print(f"STT: Model path does not exist: {MODEL_PATH}")
                return ""
            _model = vosk.Model(MODEL_PATH)
        recognizer = vosk.KaldiRecognizer(_model, 16000)
        stream = sd.InputStream(samplerate=16000, channels=1, callback=_callback)
        with stream:
            sd.sleep(4000)
        data = b"".join(list(q.queue))
        if data:
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                return result.get("text", "")
            else:
                return ""
        return ""
    except Exception as e:
        print(f"STT Error: {e}")
        return ""
    finally:
        if stream:
            stream.close()
            stream = None


def listen_continuous(callback, device=None):
    global stream, recognizer, _model
    _ensure_vosk()
    if not VOSK_OK:
        print("Vosk not available")
        return
    try:
        if _model is None:
            _model = vosk.Model(MODEL_PATH)
        recognizer = vosk.KaldiRecognizer(_model, 16000)
        with sd.InputStream(samplerate=16000, channels=1, device=device,
                           callback=lambda ind, frames, time, status: _callback(ind, frames, time, status)):
            while True:
                data = b"".join(list(q.queue))
                if data:
                    if recognizer.AcceptWaveform(data):
                        result = json.loads(recognizer.Result())
                        callback(result.get("text", ""))
                sd.sleep(100)
    except Exception as e:
        print(f"PTT continuous error: {e}")


def listen_stream_start(device=None):
    global stream, recognizer, _model, _stream_active
    _ensure_vosk()
    if not VOSK_OK:
        print("Vosk not available")
        return False
    try:
        if _model is None:
            _model = vosk.Model(MODEL_PATH)
        recognizer = vosk.KaldiRecognizer(_model, 16000)
        stream = sd.InputStream(samplerate=16000, channels=1, device=device, callback=_callback)
        stream.start()
        _stream_active = True
        return True
    except Exception as e:
        print(f"listen_stream_start error: {e}")
        return False


def listen_stream_stop():
    global stream, _stream_active
    try:
        if stream:
            stream.stop()
            stream.close()
            stream = None
        _stream_active = False
    except Exception as e:
        print(f"listen_stream_stop error: {e}")