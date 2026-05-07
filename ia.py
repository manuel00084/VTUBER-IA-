import requests
import time

# Modelos de respaldo en orden de preferencia
MODELOS = [
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "gemma2-9b-it",
]

def ask_groq(text, api_key, prompt, max_caracteres=500, reintentos=3):
    """
    Envía un mensaje a Groq y devuelve la respuesta.
    - Reintenta automáticamente si hay rate limit (429) o error de servidor (503).
    - Prueba modelos alternativos si el principal falla.
    - Siempre devuelve un string (nunca None ni excepción sin capturar).
    """
    if not api_key or api_key.strip() == "":
        return "⚠ Falta la API Key de Groq en config.txt"

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

    for modelo in MODELOS:
        for intento in range(reintentos):
            try:
                data = {
                    "messages": [
                        {"role": "system", "content": prompt_limitado},
                        {"role": "user",   "content": text}
                    ],
                    "model":       modelo,
                    "max_tokens":  120,
                    "temperature": 0.75
                }

                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=data,
                    headers=headers,
                    timeout=25
                )

                # ── Errores recuperables ──────────────────────────────────
                if r.status_code == 429:
                    # Rate limit: esperar y reintentar
                    wait = 2 ** intento   # 1s, 2s, 4s
                    time.sleep(wait)
                    continue

                if r.status_code == 503:
                    # Servidor no disponible: intentar otro modelo
                    time.sleep(1)
                    break   # sale del loop de reintentos, prueba siguiente modelo

                if r.status_code == 401:
                    return "⚠ API Key de Groq inválida. Revisa config.txt"

                if r.status_code == 400:
                    # Bad request — posible problema con el prompt o modelo
                    break

                if r.status_code != 200:
                    # Otro error HTTP: log y reintento
                    time.sleep(1)
                    continue

                # ── Respuesta exitosa ─────────────────────────────────────
                respuesta = r.json()["choices"][0]["message"]["content"].strip()

                # Limpiar markdown que algunos modelos agregan
                for char in ["*", "#", "`", "_"]:
                    respuesta = respuesta.replace(char, "")

                # Truncar si excede el límite
                if len(respuesta) > max_caracteres:
                    respuesta = respuesta[:max_caracteres].rsplit(" ", 1)[0] + "..."

                return respuesta if respuesta else "Hmm, no supe qué decir..."

            except requests.exceptions.Timeout:
                # Timeout: reintento inmediato
                time.sleep(0.5)
                continue

            except requests.exceptions.ConnectionError:
                return "⚠ Sin conexión a internet. Revisa tu red."

            except (KeyError, IndexError):
                # Respuesta mal formada de Groq
                time.sleep(1)
                continue

            except Exception as e:
                # Error inesperado: registrar y continuar
                time.sleep(0.5)
                continue

    # Si todos los modelos y reintentos fallaron
    return "⚠ Groq no está respondiendo. Intenta de nuevo en un momento."
