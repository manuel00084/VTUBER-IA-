import requests

def ask_groq(text, api_key, prompt, max_caracteres=500):
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Agregar instrucción de brevedad al prompt
        prompt_limitado = f"{prompt}\n\nIMPORTANTE: Responde en máximo 500 caracteres. Sé breve y concisa."

        data = {
            "messages": [
                {"role": "system", "content": prompt_limitado},
                {"role": "user", "content": text}
            ],
            "model": "llama-3.1-8b-instant",
            "max_tokens": 150,  # Limita tokens generados (~500 caracteres)
            "temperature": 0.7
        }

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=data,
            headers=headers,
            timeout=20
        )

        if r.status_code != 200:
            return f"Error IA ({r.status_code})"

        respuesta = r.json()["choices"][0]["message"]["content"]

        # Truncar si aún excede el límite
        if len(respuesta) > max_caracteres:
            respuesta = respuesta[:max_caracteres].rsplit(' ', 1)[0] + "..."

        return respuesta

    except Exception as e:
        return f"Error IA: {e}"