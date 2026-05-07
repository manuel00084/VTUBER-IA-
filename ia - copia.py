import requests

def ask_groq(text, api_key, prompt):
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            "model": "llama-3.1-8b-instant"
        }

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=data,
            headers=headers,
            timeout=20
        )

        if r.status_code != 200:
            return f"Error IA ({r.status_code})"

        return r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        return f"Error IA: {e}"