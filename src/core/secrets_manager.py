import os
import base64
import hashlib

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.txt")
SECRETS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "secrets.enc")

ENCRYPTION_PASSWORD = "KarinVTuber2024SecretKey!"

SENSITIVE_KEYS = {
    "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "TWITCH_TOKEN",
    "GROQ_API_KEY", "CEREBRAS_API_KEY", "GOOGLE_STUDIO_API_KEY",
    "FISH_API_KEY",
}


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

def _normalizar_voz(voz):
    """Convierte es_MX-Name → es-MX-Name (guión bajo a guión)"""
    if isinstance(voz, str) and "_" in voz:
        partes = voz.split("-", 1)
        if len(partes) == 2 and "_" in partes[0]:
            partes[0] = partes[0].replace("_", "-")
            return "-".join(partes)
    return voz

def load_config():
    cfg = _load_config()
    secrets = _load_secrets()
    cfg.update(secrets)
    for k in list(cfg.keys()):
        if "VOICE" in k.upper() or k in ("COMENTARISTA_VOICE", "SUBTITULOS_VOICE",
                                          "BOT_IA_VOICE", "BOT_VOICE_MALE", "BOT_VOICE_FEMALE"):
            cfg[k] = _normalizar_voz(cfg.get(k, ""))
    return cfg

def save_config(config):
    non_sensitive = {}
    sensitive_updates = {}
    for k, v in config.items():
        val = _normalizar_voz(str(v).strip()) if "VOICE" in k.upper() else str(v).strip()
        if not val:
            continue
        if k in SENSITIVE_KEYS:
            sensitive_updates[k] = val
        else:
            non_sensitive[k] = val
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            for k, v in non_sensitive.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        print("Error guardando config:", e)
    secrets = _load_secrets()
    changed = False
    for k, v in sensitive_updates.items():
        if secrets.get(k) != v:
            secrets[k] = v
            changed = True
    if changed:
        _save_secrets(secrets)


def _migrate_plaintext_secrets():
    """Move API keys from config.txt to secrets.enc and remove from config.txt"""
    if not os.path.exists(CONFIG_PATH):
        return
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        secrets = _load_secrets()
        changed_secrets = False
        new_lines = []
        migrated = False
        for line in lines:
            stripped = line.strip()
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k in SENSITIVE_KEYS and v:
                    if secrets.get(k) != v:
                        secrets[k] = v
                        changed_secrets = True
                    migrated = True
                    continue
            new_lines.append(line)
        if migrated:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print(f"[SECURITY] Migradas {sum(1 for l in lines if '=' in l and l.split('=',1)[0].strip() in SENSITIVE_KEYS)} claves de config.txt a secrets.enc")
        if changed_secrets:
            _save_secrets(secrets)
    except Exception as e:
        print(f"[SECURITY] Error migrando secretos: {e}")

_migrate_plaintext_secrets()