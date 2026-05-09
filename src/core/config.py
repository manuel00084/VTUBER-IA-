import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.txt")

def load_config():
    config = {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    config[k.strip()] = v.strip()
    except Exception as e:
        print("Error config:", e)
    return config

def save_config(config):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            for k, v in config.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        print("Error guardando config:", e)