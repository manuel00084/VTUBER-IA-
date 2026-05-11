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
            print("[ERROR] Error creando memoria:", e)
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
        print("[ERROR] Error guardando memoria:", e)


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


# emocion: 0=neutral, 1=happy, 2=excited, 3=angry, 4=sad, 5=sick, 6=bored
def update_mood(memory, user, text):
    if user not in memory:
        return

    positivos = ["gracias", "te quiero", "genial", "buena", "amo", "like", "jaja", "lol", "xD", "😄", "❤️", "best", "awesome", "good"]
    negativos = ["odio", "tonto", "malo", "callate", "fea", "triste", "sad", "wtf", "que mal", "gay"]
    excitados = ["wow", "increible", "no puedo creer", "holy", "guau", "madre mia", "awesome", "epic", "fail"]
    aburridos = ["aburrido", "que flojo", "nada", "meh", "pofa", "please", "lazy"]
    enferizos = ["enfermo", "malito", "dolor", "hurt", "sick", "me duele", "ugh", "tos"]

    t = text.lower()
    emot = memory[user].get("emotion", 0)

    for p in positivos:
        if p in t:
            emot = 1
    for n in negativos:
        if n in t:
            emot = 3
    for e in excitados:
        if e in t:
            emot = 2
    for a in aburridos:
        if a in t:
            emot = 6
    for f in enferizos:
        if f in t:
            emot = 5

    if "mood" not in memory[user]:
        memory[user]["mood"] = 0

    memory[user]["mood"] += 1 if any(p in t for p in positivos) else -1 if any(n in t for n in negativos) else 0

    memory[user]["mood"] = max(-5, min(5, memory[user]["mood"]))
    memory[user]["emotion"] = emot


EMOTION_VOICES = {
    0: "es-MX-DaliaNeural",      # neutral
    1: "es-MX-DaliaNeural",     # happy - use same voice but slower
    2: "es-MX-LorenaNeural",    # excited - higher pitch
    3: "es-ES-ElviraNeural",    # angry
    4: "es-MX-DaliaNeural",     # sad - slower
    5: "es-AR-TomasNeural",    # sick
    6: "es-ES-ElviraNeural",     # bored
}

EMOTION_PREFIXES = {
    0: ["Oye", "Mira", "Escucha"],
    1: ["¡Oye!", "~ ¡Qué bueno verte!", "¡Hola!"],
    2: ["¡Wow!", "¡Mira!", "¡Oye!"],
    3: ["...?", "...", "Disculpa?"],
    4: ["... ", "Uh... ", "Mm... "],
    5: ["... ", "Ugh... ", "Mm... "],
    6: ["... ", "Ok... ", "Si... "],
}


def add_message(memory, user, text):
    if user not in memory:
        memory[user] = {
            "history": [],
            "data": [],
            "mood": 0,
            "emotion": 0
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


def clear_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[ERROR] Error borrando memoria:", e)