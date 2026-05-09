"""
oauth_server.py
"""
import http.server, threading, webbrowser, urllib.parse, requests

CONFIG_PATH = None

def _get_config_path():
    global CONFIG_PATH
    if CONFIG_PATH is None:
        import os
        CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.txt")
    return CONFIG_PATH

REDIRECT_URI = "http://localhost:3000"
SCOPES = "chat:read chat:edit user:read:email"

def _load_config():
    cfg = {}
    try:
        with open(_get_config_path(), "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg

def _save_config(cfg):
    try:
        with open(_get_config_path(), "w", encoding="utf-8") as f:
            for k, v in cfg.items():
                f.write(f"{k}={v}\n")
    except:
        pass

def get_client_id():
    return _load_config().get("TWITCH_CLIENT_ID", "").strip()

def get_client_secret():
    return _load_config().get("TWITCH_CLIENT_SECRET", "").strip()

def _exchange_code(code):
    client_id = get_client_id()
    client_secret = get_client_secret()
    r = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": client_id, "client_secret": client_secret,
        "code": code, "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI
    }, timeout=10)
    data = r.json()
    if "access_token" not in data:
        print(f"Twitch OAuth error: {data}")
        return None
    return data.get("access_token")

def _get_user(token):
    client_id = get_client_id()
    r = requests.get("https://api.twitch.tv/helix/users",
        headers={"Authorization": f"Bearer {token}", "Client-Id": client_id}, timeout=10)
    d = r.json().get("data", [])
    return {"login": d[0]["login"]} if d else {}

class _Handler(http.server.BaseHTTPRequestHandler):
    callback = None
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" not in params:
            self._r(400, "Error: sin codigo."); return
        token = _exchange_code(params["code"][0])
        if not token:
            self._r(500, "Error con el token."); return
        user = _get_user(token)
        nick = user.get("login", "")
        cfg = _load_config()
        cfg.update({"TWITCH_TOKEN": token, "NICK": nick, "CHANNEL": nick})
        _save_config(cfg)
        self._r(200, f'<html><body style="font-family:sans-serif;text-align:center;margin-top:80px;background:#1a1a2e;color:#eaeaea"><h2 style="color:#9B59B6">Conectado como <b>{nick}</b></h2><p>Cierra esta ventana y vuelve a la app.</p><script>setTimeout(()=>window.close(),2000)</script></body></html>')
        if _Handler.callback:
            threading.Thread(target=_Handler.callback, args=(token, nick, nick), daemon=True).start()
    def _r(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())
    def log_message(self, *a): pass

class TwitchOAuth:
    def __init__(self, on_success, on_error=None):
        self.on_success = on_success
        self.on_error = on_error
    def start(self):
        _Handler.callback = self.on_success
        try:
            srv = http.server.HTTPServer(("localhost", 3000), _Handler)
        except OSError:
            if self.on_error: self.on_error("Puerto 3000 ocupado.")
            return
        client_id = get_client_id()
        auth_url = (f"https://id.twitch.tv/oauth2/authorize"
                    f"?client_id={client_id}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
                    f"&response_type=code&scope={urllib.parse.quote(SCOPES)}")
        webbrowser.open(auth_url)
        threading.Thread(target=lambda: (srv.handle_request(), srv.server_close()), daemon=True).start()

def validate_token(token):
    try:
        r = requests.get("https://id.twitch.tv/oauth2/validate",
                        headers={"Authorization": f"OAuth {token.strip()}"}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def clear_token():
    cfg = _load_config()
    if "TWITCH_TOKEN" in cfg:
        del cfg["TWITCH_TOKEN"]
        _save_config(cfg)