import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(BASE_DIR, "data", "memoria.json")

MAX_USERS = 200
MAX_MESSAGES = 10


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)
            return {}
        except Exception as e:
            print("❌ Error creando memoria:", e)
            return {}

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_memory(memory):
    try:
        tmp_file = MEMORY_FILE + ".tmp"

        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)

        os.replace(tmp_file, MEMORY_FILE)

    except Exception as e:
        print("❌ Error guardando memoria:", e)


# 🧠 detectar info importante
def is_important(text):
    text = text.lower()

    claves = [
        "me llamo",
        "mi nombre es",
        "soy",
        "me gusta",
        "mi juego",
        "trabajo",
        "tengo",
        "cumplo"
    ]

    return any(c in text for c in claves)


# 💖 memoria emocional
def update_mood(memory, user, text):
    if user not in memory:
        return

    positivos = ["gracias", "te quiero", "genial", "buena", "amo", "like"]
    negativos = ["odio", "tonto", "malo", "callate", "fea"]

    score = 0
    t = text.lower()

    for p in positivos:
        if p in t:
            score += 1

    for n in negativos:
        if n in t:
            score -= 1

    if "mood" not in memory[user]:
        memory[user]["mood"] = 0

    memory[user]["mood"] += score

    # limitar
    memory[user]["mood"] = max(-5, min(5, memory[user]["mood"]))


def add_message(memory, user, text):
    if user not in memory:
        memory[user] = {
            "history": [],
            "data": [],
            "mood": 0
        }

    memory[user]["history"].append(text)
    if len(memory[user]["history"]) > MAX_MESSAGES:
        memory[user]["history"] = memory[user]["history"][-MAX_MESSAGES:]

    if is_important(text):
        memory[user]["data"].append(text)
        if len(memory[user]["data"]) > 20:
            memory[user]["data"] = memory[user]["data"][-20:]

    if len(memory) > MAX_USERS:
        first_key = list(memory.keys())[0]
        del memory[first_key]

    return memory


def get_context(memory, user):
    if user not in memory:
        return ""

    hist = memory[user].get("history", [])
    data = memory[user].get("data", [])
    mood = memory[user].get("mood", 0)

    contexto = ""

    # 💖 estado emocional
    if mood >= 3:
        contexto += "El usuario te cae muy bien.\n"
    elif mood >= 1:
        contexto += "El usuario te cae bien.\n"
    elif mood <= -3:
        contexto += "El usuario te cae mal.\n"
    elif mood <= -1:
        contexto += "El usuario te cae un poco mal.\n"

    if data:
        contexto += "\nDatos importantes:\n"
        contexto += "\n".join(data) + "\n"

    if hist:
        contexto += "\nHistorial:\n"
        contexto += "\n".join(hist)

    return contexto