"""
setup_wizard.py
---------------
Todas las credenciales sensibles van en secrets.enc (encriptadas).
"""
import customtkinter as ctk
import webbrowser

from src.core.secrets_manager import set_secret, get_secret, load_config

PURPLE     = "#9B59B6"
PURPLE_DRK = "#7D3C98"
PINK       = "#E91E8C"
DARK_BG    = "#1A1A2E"
CARD_BG    = "#16213E"
ENTRY_BG   = "#0F3460"
TEXT_WHITE = "#EAEAEA"
TEXT_GRAY  = "#A0A0C0"
GREEN_OK   = "#2ECC71"
RED_ERR    = "#E74C3C"


class SetupWizard(ctk.CTkToplevel):
    def __init__(self, parent, existing_config: dict, on_done):
        super().__init__(parent)
        self.on_done = on_done
        self.cfg = dict(existing_config)

        self.title("⚙️  Configuración — VTuber IA")
        self.geometry("580x700")
        self.resizable(False, False)
        self.configure(fg_color=DARK_BG)
        self.grab_set()

        ctk.CTkLabel(self, text="🎀  Configuración de VTuber IA",
            font=("Georgia", 22, "bold"), text_color=PINK,
        ).pack(pady=(20, 4))

        ctk.CTkLabel(self, text="Los datos sensibles están encriptados en secrets.enc",
            font=("Helvetica", 12), text_color=TEXT_GRAY, wraplength=520,
        ).pack(pady=(0, 16))

        scroll = ctk.CTkScrollableFrame(self, fg_color=DARK_BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=20, pady=0)

        self._section_twitch(scroll)
        self._section_ia(scroll)
        self._section_bot(scroll)

        self.status_lbl = ctk.CTkLabel(self, text="", font=("Helvetica", 12), text_color=TEXT_GRAY)
        self.status_lbl.pack(pady=(6, 0))

        ctk.CTkButton(self, text="💾  Guardar y continuar",
            font=("Helvetica", 14, "bold"),
            fg_color=PURPLE, hover_color=PURPLE_DRK,
            corner_radius=12, height=44,
            command=self._save,
        ).pack(pady=(10, 20), padx=40, fill="x")

    def _card(self, parent, title: str, link_text: str = "", link_url: str = ""):
        frame = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12)
        frame.pack(fill="x", pady=8)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(header, text=title, font=("Helvetica", 14, "bold"),
            text_color=PURPLE).pack(side="left")
        if link_text and link_url:
            btn = ctk.CTkLabel(header, text=f"🔗 {link_text}", font=("Helvetica", 11),
                text_color=PINK, cursor="hand2")
            btn.pack(side="right")
            btn.bind("<Button-1>", lambda e: webbrowser.open(link_url))
        return frame

    def _field(self, parent, label: str, key: str, placeholder: str = "",
               show: str = "", hint: str = ""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row, text=label, font=("Helvetica", 12),
            text_color=TEXT_WHITE, anchor="w", width=140).pack(side="left")
        var = ctk.StringVar(value=self.cfg.get(key, ""))
        entry = ctk.CTkEntry(row, textvariable=var, placeholder_text=placeholder,
            show=show, fg_color=ENTRY_BG, border_color=PURPLE,
            text_color=TEXT_WHITE, width=320, corner_radius=8)
        entry.pack(side="left", padx=(8, 0))
        var.trace_add("write", lambda *_: self.cfg.update({key: var.get()}))
        if hint:
            ctk.CTkLabel(parent, text=f"   ℹ️ {hint}", font=("Helvetica", 10),
                text_color=TEXT_GRAY, anchor="w").pack(fill="x", padx=16, pady=(0, 2))

    def _section_twitch(self, parent):
        card = self._card(parent, "🎮  Twitch", "Obtener credenciales",
            "https://dev.twitch.tv/console")
        self._field(card, "Client ID",     "TWITCH_CLIENT_ID",
            "4t7kth7bzynj...", hint="dev.twitch.tv → tu app → ID de cliente")
        self._field(card, "Client Secret", "TWITCH_CLIENT_SECRET",
            "••••••••", show="•", hint="Mismo panel → Nuevo secreto")
        self._field(card, "Canal",          "CHANNEL",
            "mi_canal", hint="Nombre de tu canal (sin @)")
        self._field(card, "Nick",           "NICK",
            "mi_canal", hint="Tu usuario de Twitch")
        ctk.CTkButton(card, text="🔑  Autorizar con Twitch (abre navegador)",
            font=("Helvetica", 11), fg_color="#9146FF", hover_color="#772CE8",
            command=self._oauth_twitch, height=32,
        ).pack(padx=16, pady=(4, 12), fill="x")

    def _section_ia(self, parent):
        card = self._card(parent, "🤖  API Keys IA", "Groq gratuito",
            "https://console.groq.com/keys")
        self._field(card, "Groq API Key", "GROQ_API_KEY",
            "gsk_...", show="•", hint="Groq es gratuito")
        ctk.CTkLabel(card, text="   ✅  Groq no requiere tarjeta de crédito.",
            font=("Helvetica", 10), text_color=GREEN_OK, anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 12))

    def _section_bot(self, parent):
        card = self._card(parent, "🔧  Comandos del bot")
        ctk.CTkLabel(card, text=(
            "   !sp <texto>  → leer con voz hombre\n"
            "   !spm <texto> → leer con voz mujer\n"
            "   !IA <texto>  → hablar con la IA VTuber\n"
            "   F9 (en app)  → Push-to-Talk con IA"
        ), font=("Courier", 11), text_color=TEXT_GRAY, justify="left", anchor="w",
        ).pack(fill="x", padx=16, pady=(4, 12))

    def _oauth_twitch(self):
        self._set_status("Abriendo navegador... Autoriza y vuelve aquí.", TEXT_GRAY)
        try:
            from src.core.oauth_server import TwitchOAuth
            oauth = TwitchOAuth(
                on_success=lambda token, nick, channel: self.after(0, lambda: self._on_oauth_success(nick)),
                on_error=lambda e: self.after(0, lambda: self._set_status(f"❌ {e}", RED_ERR))
            )
            oauth.start()
        except Exception as e:
            self._set_status(f"❌ Error: {e}", RED_ERR)

    def _on_oauth_success(self, nick):
        self.cfg["NICK"] = nick
        self.cfg["CHANNEL"] = nick
        self._set_status(f"✅ Conectado como {nick}. Ahora guarda la config.", GREEN_OK)

    def _save(self):
        required = {
            "TWITCH_CLIENT_ID":      "Client ID",
            "TWITCH_CLIENT_SECRET":   "Client Secret",
            "CHANNEL":               "Canal",
            "NICK":                  "Nick",
            "GROQ_API_KEY":          "Groq API Key",
        }
        for key, label in required.items():
            if not self.cfg.get(key, "").strip():
                self._set_status(f"❌  Falta: {label}", RED_ERR)
                return

        for key, value in self.cfg.items():
            if value.strip():
                set_secret(key, value.strip())

        self._set_status("✅  Configuración guardada (encriptada).", GREEN_OK)
        self.after(1200, self._finish)

    def _finish(self):
        self.on_done(load_config())
        self.destroy()

    def _set_status(self, msg: str, color: str):
        self.status_lbl.configure(text=msg, text_color=color)


def needs_setup(config: dict) -> bool:
    required = ["TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "CHANNEL", "NICK", "GROQ_API_KEY"]
    return any(not config.get(k, "").strip() for k in required)


def open_setup_if_needed(parent, config: dict, on_done):
    if needs_setup(config):
        SetupWizard(parent, config, on_done)
    else:
        on_done(config)