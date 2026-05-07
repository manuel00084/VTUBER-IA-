"""
setup_wizard.py
---------------
Ventana de configuración guiada para VTuber IA.
Se abre automáticamente la primera vez que el usuario no tiene config.txt completo.
Compatible con el config.py y main.py existentes del proyecto.
"""

import customtkinter as ctk
import webbrowser
import os

# ─── Colores del tema VTuber ───────────────────────────────────────────────
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
YELLOW     = "#F1C40F"


class SetupWizard(ctk.CTkToplevel):
    """
    Ventana modal de configuración paso a paso.
    Llama a `on_done(config_dict)` cuando el usuario guarda.
    """

    def __init__(self, parent, save_config_fn, existing_config: dict, on_done):
        super().__init__(parent)
        self.save_config = save_config_fn
        self.on_done = on_done
        self.cfg = dict(existing_config)          # copia mutable

        # ── Ventana ────────────────────────────────────────────────────────
        self.title("⚙️  Configuración inicial — VTuber IA")
        self.geometry("580x700")
        self.resizable(False, False)
        self.configure(fg_color=DARK_BG)
        self.grab_set()                           # bloquea la ventana padre

        # ── Título ─────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="🎀  Configuración de VTuber IA",
            font=("Georgia", 22, "bold"),
            text_color=PINK,
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            self,
            text="Rellena los datos a continuación para conectar con Twitch y Groq IA.",
            font=("Helvetica", 12),
            text_color=TEXT_GRAY,
            wraplength=520,
        ).pack(pady=(0, 16))

        # ── Scroll frame principal ─────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color=DARK_BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=20, pady=0)

        # ── Secciones ─────────────────────────────────────────────────────
        self._section_twitch(scroll)
        self._section_groq(scroll)
        self._section_bot(scroll)

        # ── Barra de estado ────────────────────────────────────────────────
        self.status_lbl = ctk.CTkLabel(
            self, text="", font=("Helvetica", 12), text_color=TEXT_GRAY
        )
        self.status_lbl.pack(pady=(6, 0))

        # ── Botón guardar ──────────────────────────────────────────────────
        ctk.CTkButton(
            self,
            text="💾  Guardar y conectar",
            font=("Helvetica", 14, "bold"),
            fg_color=PURPLE,
            hover_color=PURPLE_DRK,
            corner_radius=12,
            height=44,
            command=self._save,
        ).pack(pady=(10, 20), padx=40, fill="x")

    # ── Helpers ────────────────────────────────────────────────────────────

    def _card(self, parent, title: str, link_text: str = "", link_url: str = ""):
        """Crea un frame tipo tarjeta con título y enlace opcional."""
        frame = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12)
        frame.pack(fill="x", pady=8)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            header,
            text=title,
            font=("Helvetica", 14, "bold"),
            text_color=PURPLE,
        ).pack(side="left")

        if link_text and link_url:
            btn = ctk.CTkLabel(
                header,
                text=f"🔗 {link_text}",
                font=("Helvetica", 11),
                text_color=PINK,
                cursor="hand2",
            )
            btn.pack(side="right")
            btn.bind("<Button-1>", lambda e: webbrowser.open(link_url))

        return frame

    def _field(self, parent, label: str, key: str, placeholder: str = "",
               show: str = "", hint: str = ""):
        """Crea una fila label + entry enlazada al config."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(
            row, text=label, font=("Helvetica", 12),
            text_color=TEXT_WHITE, anchor="w", width=140,
        ).pack(side="left")

        var = ctk.StringVar(value=self.cfg.get(key, ""))
        entry = ctk.CTkEntry(
            row,
            textvariable=var,
            placeholder_text=placeholder,
            show=show,
            fg_color=ENTRY_BG,
            border_color=PURPLE,
            text_color=TEXT_WHITE,
            width=320,
            corner_radius=8,
        )
        entry.pack(side="left", padx=(8, 0))

        # guardar referencia para leer al guardar
        self.cfg[key] = self.cfg.get(key, "")
        var.trace_add("write", lambda *_: self.cfg.update({key: var.get()}))

        if hint:
            ctk.CTkLabel(
                parent, text=f"   ℹ️ {hint}",
                font=("Helvetica", 10), text_color=TEXT_GRAY, anchor="w",
            ).pack(fill="x", padx=16, pady=(0, 2))

    # ── Secciones de configuración ─────────────────────────────────────────

    def _section_twitch(self, parent):
        card = self._card(
            parent,
            "🎮  Twitch",
            "Obtener llaves",
            "https://dev.twitch.tv/console/apps",
        )
        self._field(card, "Client ID",     "CLIENT_ID",
                    "akco617q7tr120...",
                    hint="En dev.twitch.tv → tu app → Administrar → ID de cliente")
        self._field(card, "Client Secret", "CLIENT_SECRET",
                    "diptiwoo5ms...", show="•",
                    hint="Mismo panel → botón 'Nuevo secreto'")
        self._field(card, "Token",         "TWITCH_TOKEN",
                    "7dmpcbreyv8k...", show="•",
                    hint="Obtén tu token en twitchtokengenerator.com → Chat Bot Token")
        self._field(card, "Canal",         "CHANNEL",
                    "mi_canal_twitch",
                    hint="Nombre exacto de tu canal (sin @)")
        self._field(card, "Nick (usuario)","NICK",
                    "mi_canal_twitch",
                    hint="Generalmente igual al nombre del canal")

        # Botón de ayuda rápida
        ctk.CTkButton(
            card,
            text="📖  ¿Cómo obtengo el Token?",
            font=("Helvetica", 11),
            fg_color="transparent",
            hover_color=ENTRY_BG,
            text_color=PINK,
            command=lambda: webbrowser.open("https://twitchtokengenerator.com"),
            height=28,
        ).pack(padx=16, pady=(4, 12), anchor="w")

    def _section_groq(self, parent):
        card = self._card(
            parent,
            "🤖  Groq IA",
            "Conseguir API Key",
            "https://console.groq.com/keys",
        )
        self._field(card, "Groq API Key", "GROQ_API_KEY",
                    "gsk_...", show="•",
                    hint="console.groq.com → API Keys → Create API Key (gratis)")

        ctk.CTkLabel(
            card,
            text="   ✅  Groq es gratuito — no necesitas tarjeta de crédito.",
            font=("Helvetica", 10), text_color=GREEN_OK, anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 12))

    def _section_bot(self, parent):
        card = self._card(parent, "🔧  Opciones del bot")
        ctk.CTkLabel(
            card,
            text=(
                "   Comandos disponibles en el chat de Twitch:\n"
                "   • !sp <texto>   → leer con voz neutra\n"
                "   • !spm <texto>  → leer con voz de mujer\n"
                "   • !IA <texto>   → hablar con la IA VTuber\n"
                "   • F9 (en app)   → micrófono PTT para hablar con la IA"
            ),
            font=("Courier", 11),
            text_color=TEXT_GRAY,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(4, 12))

    # ── Guardar ────────────────────────────────────────────────────────────

    def _save(self):
        # Validar campos obligatorios
        required = {
            "TWITCH_TOKEN": "Token de Twitch",
            "CHANNEL":      "Canal de Twitch",
            "NICK":         "Nick de Twitch",
            "GROQ_API_KEY": "Groq API Key",
        }
        for key, label in required.items():
            if not self.cfg.get(key, "").strip():
                self._set_status(f"❌  Falta: {label}", RED_ERR)
                return

        self.save_config(self.cfg)
        self._set_status("✅  Configuración guardada correctamente.", GREEN_OK)
        self.after(1200, self._finish)

    def _finish(self):
        self.on_done(self.cfg)
        self.destroy()

    def _set_status(self, msg: str, color: str):
        self.status_lbl.configure(text=msg, text_color=color)


# ── Función de conveniencia ────────────────────────────────────────────────

def needs_setup(config: dict) -> bool:
    """Devuelve True si faltan campos obligatorios para arrancar."""
    required = ["TWITCH_TOKEN", "CHANNEL", "NICK", "GROQ_API_KEY"]
    return any(not config.get(k, "").strip() for k in required)


def open_setup_if_needed(parent, save_config_fn, config: dict, on_done):
    """
    Llama esto desde main.py justo después de cargar la config.
    Si faltan datos abre el wizard; si todo está completo llama on_done
    directamente.

    Ejemplo de uso en main.py:
        from setup_wizard import open_setup_if_needed, needs_setup
        config = load_config()
        open_setup_if_needed(self, save_config, config, self._on_config_ready)
    """
    if needs_setup(config):
        SetupWizard(parent, save_config_fn, config, on_done)
    else:
        on_done(config)
