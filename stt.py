import sounddevice as sd
import numpy as np
import queue
import sys
import json
import vosk

import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "vosk-model-small-es-0.42")
# ===== CONFIG =====

q = queue.Queue()

def callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))

def listen():
    try:
        model = vosk.Model(MODEL_PATH)
        recognizer = vosk.KaldiRecognizer(model, 16000)

        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                               channels=1, callback=callback):

            print("🎤 Escuchando...")
            while True:
                data = q.get()
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "")
                    return text

    except Exception as e:
        print("❌ STT error:", e)
        return None
import queue

stream = None
recognizer = None
q = queue.Queue()

def listen_stream_start(app):
    global stream, recognizer

    model = vosk.Model(MODEL_PATH)
    recognizer = vosk.KaldiRecognizer(model, 16000)

    def callback(indata, frames, time, status):
        if status:
            print(status)
        q.put(bytes(indata))

    stream = sd.RawInputStream(
        samplerate=16000,
        blocksize=8000,
        dtype='int16',
        channels=1,
        callback=callback
    )
    stream.start()


def listen_stream_stop():
    global stream, recognizer

    text = ""

    try:
        while not q.empty():
            data = q.get()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")

        if stream:
            stream.stop()
            stream.close()

        return text

    except Exception as e:
        print("❌ STT stream error:", e)
        return None