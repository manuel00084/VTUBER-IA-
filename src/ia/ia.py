import requests
import time

PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "models_texto": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
        "models_vision": ["llama-3.2-11b-vision-preview", "llama-3.2-90b-vision-preview",
                          "llava-v1.5-7b-4096-preview", "meta-llama/llama-4-scout-17b-16e-instruct"],
    },
    "cerebras": {
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "models_texto": ["llama3.1-8b", "qwen-3-235b-a22b-instruct-2507", "gpt-oss-120b"],
        "models_vision": [],
    },
    "google_studio": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "models_texto": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "models_vision": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    },
}


def ask_ai(text, api_key, prompt, provider="groq", max_caracteres=500, reintentos=3, vision=False):
    """
    Envía un mensaje a un proveedor de IA y devuelve la respuesta.
    provider: 'groq', 'cerebras', etc.
    vision: True para enviar imagen (solo proveedores con models_vision)
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
        "IMPORTANTE: Responde SIEMPRE en español. "
        "Maximo 400 caracteres. "
        "Sé breve, natural y concisa. No uses asteriscos ni markdown."
    )

    cfg = PROVIDERS.get(provider)
    if not cfg:
        cfg = PROVIDERS.get("groq")
    url = cfg["url"]
    modelos = cfg.get("models_vision", []) if vision and cfg.get("models_vision") else cfg["models_texto"]
    if not modelos:
        modelos = PROVIDERS["groq"]["models_vision"] if vision else PROVIDERS["groq"]["models_texto"]

    for modelo in modelos:
        for intento in range(reintentos):
            try:
                if provider == "google_studio":
                    req_url = url.format(model=modelo) + f"?key={api_key.strip()}"
                    req_headers = {"Content-Type": "application/json"}
                    req_data = {
                        "contents": [{
                            "parts": [{"text": f"{prompt_limitado}\n\n{text}"}]
                        }],
                        "generationConfig": {
                            "maxOutputTokens": 700 if vision else 200,
                            "temperature": 0.05 if vision else 0.5,
                        }
                    }
                else:
                    req_url = url
                    req_headers = headers
                    req_data = {
                        "messages": [
                            {"role": "system", "content": prompt_limitado},
                            {"role": "user",   "content": text}
                        ],
                        "model":       modelo,
                        "max_tokens":  700 if vision else 200,
                        "temperature": 0.05 if vision else 0.5,
                    }
                r = requests.post(req_url, json=req_data, headers=req_headers, timeout=30)
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
                if provider == "google_studio":
                    respuesta = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                else:
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


def ask_vision(image_b64, texto, api_key, prompt="", modelo_idx=0, provider="groq", log=print):
    """Traduce/detecta texto en imagen usando IA con visión."""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        cfg = PROVIDERS.get("groq")
    
    if not cfg.get("models_vision"):
        if log:
            log(f"⚠ '{provider}' no tiene modelos de visión disponibles")
        return None, modelo_idx, False
    
    if provider == "google_studio":
        # Google Studio AI uses a different API format
        model_name = cfg["models_vision"][modelo_idx % len(cfg["models_vision"])]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_b64
                        }
                    }
                ]
            }]
        }
    else:
        # OpenAI-compatible format (Groq, Cerebras, etc.)
        modelos = cfg["models_vision"]
        url = cfg["url"]
        modelo = modelos[modelo_idx % len(modelos)]
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
        r = requests.post(url, json=data, headers=headers, timeout=30)
        if r.status_code == 429:
            return None, modelo_idx, True
        if r.status_code == 400:
            if log:
                try:
                    detalle = r.json().get("error", {}).get("message", r.text[:200])
                except Exception:
                    detalle = r.text[:200]
                log(f"⚠ API 400 con {provider}/{modelo}: {detalle}")
            return None, modelo_idx + 1, False
        if r.status_code != 200:
            return None, modelo_idx, False
        
        if provider == "google_studio":
            respuesta = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            respuesta = r.json()["choices"][0]["message"]["content"].strip()
        
        # Clean up common formatting characters
        for char in ["*", "#", "`", "_"]:
            respuesta = respuesta.replace(char, "")
        return respuesta, modelo_idx, False
    except:
        return None, modelo_idx, False