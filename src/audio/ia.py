import requests
import time

GROQ_MODELOS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]

CEREBRAS_MODELOS = [
    "llama3.1-8b",
    "qwen-3-235b-a22b-instruct-2507",
    "gpt-oss-120b",
]

GROQ_TEXT_MODELOS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
]

GROQ_VISION_MODELOS = [
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
    "llava-v1.5-7b-4096-preview",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]


def ask_ai(text, api_key, prompt, provider="groq", max_caracteres=500, reintentos=3, vision=False):
    """
    Envía un mensaje a Groq o Cerebras y devuelve la respuesta.
    provider: 'groq' o 'cerebras'
    vision: True para enviar imagen (Groq only)
    """
    if not api_key or api_key.strip() == "":
        return "⚠ Falta la API Key en config"

    if not text or text.strip() == "":
        return "⚠ El mensaje está vacío"

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }

    prompt_limitado = (
        f"{prompt}\n\n"
        "IMPORTANTE: Responde en máximo 400 caracteres. "
        "Sé breve, natural y concisa. No uses asteriscos ni markdown."
    )

    if provider == "cerebras":
        modelos = CEREBRAS_MODELOS
        url = "https://api.cerebras.ai/v1/chat/completions"
    else:
        modelos = GROQ_MODELOS if vision else GROQ_TEXT_MODELOS
        url = "https://api.groq.com/openai/v1/chat/completions"

    for modelo in modelos:
        for intento in range(reintentos):
            try:
                if vision and provider == "groq":
                    data = {
                        "messages": [
                            {"role": "system", "content": prompt_limitado},
                            {"role": "user",   "content": text}
                        ],
                        "model":       modelo,
                        "max_tokens":  700,
                        "temperature": 0.05
                    }
                else:
                    data = {
                        "messages": [
                            {"role": "system", "content": prompt_limitado},
                            {"role": "user",   "content": text}
                        ],
                        "model":       modelo,
                        "max_tokens":  120,
                        "temperature": 0.75
                    }

                r = requests.post(url, json=data, headers=headers, timeout=30)

                if r.status_code == 429:
                    time.sleep(2 ** intento)
                    continue

                if r.status_code == 503:
                    time.sleep(1)
                    break

                if r.status_code == 401:
                    return "⚠ API Key inválida"

                if r.status_code in (400, 404):
                    break

                if r.status_code != 200:
                    time.sleep(1)
                    continue

                respuesta = r.json()["choices"][0]["message"]["content"].strip()
                for char in ["*", "#", "`", "_"]:
                    respuesta = respuesta.replace(char, "")

                if len(respuesta) > max_caracteres:
                    respuesta = respuesta[:max_caracteres].rsplit(" ", 1)[0] + "..."

                return respuesta if respuesta else "Hmm, no supe qué decir..."

            except requests.exceptions.Timeout:
                time.sleep(0.5)
                continue

            except requests.exceptions.ConnectionError:
                return "⚠ Sin conexión a internet"

            except (KeyError, IndexError):
                time.sleep(1)
                continue

            except Exception:
                time.sleep(0.5)
                continue

    return "⚠ El servicio no está respondiendo. Intenta más tarde."


def ask_groq(text, api_key, prompt, max_caracteres=500, reintentos=3):
    return ask_ai(text, api_key, prompt, provider="groq", max_caracteres=max_caracteres, reintentos=reintentos)

def ask_cerebras(text, api_key, prompt, max_caracteres=500, reintentos=3):
    return ask_ai(text, api_key, prompt, provider="cerebras", max_caracteres=max_caracteres, reintentos=reintentos)


def ask_vision(image_b64, texto, api_key, prompt, modelo_idx=0, log=print):
    """Traduce/detecta texto en imagen usando Groq Vision."""
    modelo = GROQ_VISION_MODELOS[modelo_idx % len(GROQ_VISION_MODELOS)]
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
    data = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": texto}
            ]}
        ],
        "max_tokens": 700,
        "temperature": 0.05,
    }
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          json=data, headers=headers, timeout=30)
        if r.status_code == 429:
            return None, modelo_idx, True
        if r.status_code == 400:
            return None, modelo_idx + 1, False
        if r.status_code != 200:
            return None, modelo_idx, False
        return r.json()["choices"][0]["message"]["content"].strip(), modelo_idx, False
    except:
        return None, modelo_idx, False