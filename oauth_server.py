"""
oauth_server.py
---------------
Las credenciales estan encriptadas en secrets_manager.py
nadie que abra este archivo ve el Client ID ni el Secret real.
"""
import http.server, threading, webbrowser, urllib.parse, os, requests
from secrets_manager import get_client_id, get_client_secret

CLIENT_ID     = get_client_id()
CLIENT_SECRET = get_client_secret()

REDIRECT_URI = "http://localhost:3000"
SCOPES       = "chat:read chat:edit"
AUTH_URL     = (
    f"https://id.twitch.tv/oauth2/authorize"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&response_type=code"
    f"&scope={urllib.parse.quote(SCOPES)}"
)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.txt")

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

def _save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        for k, v in cfg.items():
            f.write(f"{k}={v}\n")

def _exchange_code(code):
    r = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "code": code, "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI
    }, timeout=10)
    return r.json().get("access_token")

def _get_user(token):
    r = requests.get("https://api.twitch.tv/helix/users",
        headers={"Authorization": f"Bearer {token}", "Client-Id": CLIENT_ID}, timeout=10)
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
        webbrowser.open(AUTH_URL)
        threading.Thread(target=lambda: (srv.handle_request(), srv.server_close()), daemon=True).start()
