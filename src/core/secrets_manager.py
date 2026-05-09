import os
import base64
import hashlib

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.txt")
SECRETS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "secrets.enc")

ENCRYPTION_PASSWORD = "KarinVTuber2024SecretKey!"

def _get_key():
    key = hashlib.sha256(ENCRYPTION_PASSWORD.encode()).digest()
    return base64.urlsafe_b64encode(key)

def _load_secrets():
    if not os.path.exists(SECRETS_PATH):
        return {}
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            from cryptography.fernet import Fernet
            fernet = Fernet(_get_key())
            data = base64.b64decode(content)
            decrypted = fernet.decrypt(data).decode()
            secrets = {}
            for line in decrypted.split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    secrets[k.strip()] = v.strip()
            return secrets
    except Exception:
        return {}

def _save_secrets(secrets):
    from cryptography.fernet import Fernet
    fernet = Fernet(_get_key())
    raw = "\n".join(f"{k}={v}" for k, v in secrets.items())
    encrypted = fernet.encrypt(raw.encode())
    encoded = base64.b64encode(encrypted).decode()
    with open(SECRETS_PATH, "w", encoding="utf-8") as f:
        f.write(encoded)

def get_secret(key_name, default=""):
    return _load_secrets().get(key_name, default)

def set_secret(key_name, value):
    secrets = _load_secrets()
    secrets[key_name] = value
    _save_secrets(secrets)

def clear_secret(key_name):
    secrets = _load_secrets()
    if key_name in secrets:
        del secrets[key_name]
        _save_secrets(secrets)

def _load_config():
    cfg = {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg

def load_config():
    cfg = _load_config()
    secrets = _load_secrets()
    cfg.update(secrets)
    return cfg

def save_config(config):
    non_sensitive = {}
    for k, v in config.items():
        if k in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"):
            continue
        non_sensitive[k] = v
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            for k, v in non_sensitive.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        print("Error guardando config:", e)
    secrets = _load_secrets()
    changed = False
    for k in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"):
        if k in config and config[k].strip():
            if secrets.get(k) != config[k]:
                secrets[k] = config[k]
                changed = True
    if changed:
        _save_secrets(secrets)

def get_twitch_client_id():
    return get_secret("TWITCH_CLIENT_ID", "")

def get_twitch_client_secret():
    return get_secret("TWITCH_CLIENT_SECRET", "")

def get_all_api_keys():
    s = _load_secrets()
    return {
        "GROQ_API_KEY": s.get("GROQ_API_KEY", ""),
        "CEREBRAS_API_KEY": s.get("CEREBRAS_API_KEY", ""),
        "GOOGLE_API_KEY": s.get("GOOGLE_API_KEY", ""),
    }

def save_all_api_keys(groq_key, cerebras_key, google_key):
    secrets = _load_secrets()
    if groq_key:
        secrets["GROQ_API_KEY"] = groq_key
    if cerebras_key:
        secrets["CEREBRAS_API_KEY"] = cerebras_key
    if google_key:
        secrets["GOOGLE_API_KEY"] = google_key
    _save_secrets(secrets)