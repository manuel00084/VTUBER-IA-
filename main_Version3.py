import customtkinter as ctk
import threading
import os
from PIL import Image, ImageTk

# ============  SEGURIDAD EN IMPORTS (igual que tu versión) =============
try:
    from config import load_config, save_config
except Exception as e:
    print("Error config:", e)
    load_config = lambda: {}
    save_config = lambda x: None

try:
    from audio import audio_worker, speak, stop_audio
except Exception as e:
    print("Error audio:", e)
    def audio_worker(): pass
    def speak(*args, **kwargs): print("speak fallback:", args)
    def stop_audio(): pass

try:
    from ia import ask_groq
except Exception as e:
    print("Error ia:", e)
    def ask_groq(*args, **kwargs): return "IA no disponible"

try:
    from devices import get_output_devices
except Exception as e:
    print("Error devices:", e)
    def get_output_devices(): return [("Default", 0)]

try:
    from twitch_bot import start_chat
except Exception as e:
    print("Error twitch_bot:", e)
    def start_chat(*args, **kwargs): print("Twitch deshabilitado")

try:
    from ptt import PTTManager
except Exception as e:
    print("Error ptt:", e)
    PTTManager = None

try:
    from game_watcher import GameWatcher
except Exception as e:
    print("Error game_watcher:", e)
    GameWatcher = None

try:
    from translator import TranslatorManager
except Exception as e:
    print("Error translator:", e)
    TranslatorManager = None

config = load_config()

VIBRANT_PINK = "#ff5ad3"
SOFT_PURPLE = "#9F6AFF"
SOFT_CYAN = "#7fffff"
DEEP_PURPLE = "#583A97"
BG_HEADER = "#251d3a"
BG_ACCENT = "#292040"
AVATAR_FILE = "vtuber.png"
FONT_TITLE = ("Arial Rounded MT Bold", 26, "bold")
FONT_LOGS = ("Consolas", 11)
FONT_ACCENT = ("Comic Sans MS", 12, "bold")  # Cambia si tienes otra favorita

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("˗ˏˋ VTuber-IA ✦ Interfaz Next-Gen ˎˊ˗ ")
        self.geometry("600x900")
        self.resizable(width=False, height=False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # ===== THREAD audio separado====
        threading.Thread(target=audio_worker, daemon=True).start()

        # ======= HEADER + AVATAR ========
        header = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0)
        header.pack(fill="x")
        avatar_path = os.path.join(os.path.dirname(__file__), AVATAR_FILE)
        header_row = ctk.CTkFrame(header, fg_color=BG_HEADER)
        header_row.pack(pady=(8,0), padx=0, fill="x")
        # Avatar (opcional)
        if os.path.exists(avatar_path):
            img = Image.open(avatar_path).resize((80,80))
            self.avatar_img = ImageTk.PhotoImage(img)
            ctk.CTkLabel(header_row, image=self.avatar_img, text="").pack(side="left", padx=(8,8))
        ctk.CTkLabel(header_row, text="✨ VTuber-IA ✨", font=FONT_TITLE, text_color=SOFT_CYAN).pack(side="left", padx=(0,10))
        # Subtítulo friendly
        ctk.CTkLabel(header, text="¡Tu asistente VTuber con IA, streaming y magia kawaii!", text_color=SOFT_PURPLE, font=FONT_ACCENT).pack(pady=(2,0))

        # === USER/Estado "En vivo" tipo streaming ===
        self.status_bar = ctk.CTkLabel(header, text="🟢 Online | Listo para brillar y conversar", font=("Arial", 11), text_color=VIBRANT_PINK)
        self.status_bar.pack(pady=(4,12))

        # =========== PROMPT SELECT ==============
        self.promt_folder = os.path.join(os.path.dirname(__file__), "PROMT")
        os.makedirs(self.promt_folder, exist_ok=True)
        self.promt_files = [f for f in os.listdir(self.promt_folder) if f.endswith(".txt")]
        if not self.promt_files:
            default_path = os.path.join(self.promt_folder, "default.txt")
            with open(default_path, "w", encoding="utf-8") as f:
                f.write("Eres una VTuber divertida.")
            self.promt_files = ["default.txt"]
        self.current_prompt = "Eres una VTuber divertida."
        prompt_sel = ctk.CTkFrame(self, fg_color=BG_ACCENT, corner_radius=12)
        prompt_sel.pack(pady=(18,8), padx=20, fill="x")
        ctk.CTkLabel(prompt_sel, text="🎭 Elegir personalidad/rol:", font=FONT_ACCENT, text_color="#ffcaff").pack(side="left", padx=16, pady=12)
        self.prompt_var = ctk.StringVar(value=self.promt_files[0])
        self.prompt_menu = ctk.CTkComboBox(prompt_sel, values=self.promt_files, variable=self.prompt_var, width=170, font=("Arial", 13), command=self.set_prompt)
        self.prompt_menu.pack(side="left", padx=8)
        ctk.CTkButton(prompt_sel, text="🌈 Recargar", fg_color=SOFT_PURPLE, command=self.reload_prompts, hover_color=DEEP_PURPLE).pack(side="right", padx=18)
        
        # ========== LOGS (grande y bonito) ============
        logs_frame = ctk.CTkFrame(self, fg_color="#18122B", corner_radius=16)
        logs_frame.pack(fill="both", expand=True, padx=18, pady=(8,8))
        ctk.CTkLabel(logs_frame, text="📝 Registro kawaii de la sesión", font=("Arial Rounded MT Bold", 15), text_color=SOFT_CYAN).pack(anchor="w", padx=12, pady=4)
        self.logs = ctk.CTkTextbox(logs_frame, height=200, font=FONT_LOGS, fg_color="#201344", text_color="#fff6fe")
        self.logs.pack(fill="both", expand=True, padx=12, pady=(0,14))

        # ========== ACCIONES VTUBERIALES ============
        actions = ctk.CTkFrame(self, fg_color=BG_ACCENT, corner_radius=12)
        actions.pack(fill="x", padx=15, pady=(4,12))
        ctk.CTkLabel(actions, text="✨ Acciones express:", font=FONT_ACCENT, text_color="#ffb0e3").pack(anchor="w", padx=8, pady=(6,4))
        btns = [
            ("🧪 Test GUI", self.test_log, VIBRANT_PINK),
            ("🎤 Test Voz", self.test_voice, SOFT_PURPLE),
            ("🤖 Test IA", self.test_ia, SOFT_CYAN),
            ("💬 Conectar Twitch", self.connect_twitch, "#61dfff"),
            ("🔊 Hablar con IA", self.ptt_click, "#f7b3fa")
        ]
        for txt, cmd, color in btns:
            ctk.CTkButton(actions, text=txt, command=cmd, fg_color=color, hover_color="#222030", font=FONT_ACCENT).pack(fill="x", pady=3, padx=10)

        # === MENSAJE FLASH STATE =====
        self.flash_label = ctk.CTkLabel(self, text="", text_color=SOFT_CYAN, font=FONT_ACCENT)
        self.flash_label.pack(fill="x", padx=20, pady=(0,10))

    # --- Acciones y lógica de controles ----
    def set_prompt(self, selected):
        try:
            with open(os.path.join(self.promt_folder, selected), encoding="utf-8") as f:
                self.current_prompt = f.read()
            self.kawaii_log(f"✨ Prompt cambiado a: {selected}")
            self.flash("✅ Prompt cargado: " + selected, "#99ffcc")
        except Exception as e:
            self.kawaii_log("Error cargando prompt: " + str(e))
            self.flash("❌ Error al cargar prompt", "#ff7777")
    
    def reload_prompts(self):
        self.promt_files = [f for f in os.listdir(self.promt_folder) if f.endswith(".txt")]
        self.prompt_menu.configure(values=self.promt_files)
        if self.promt_files:
            self.prompt_var.set(self.promt_files[0])
        self.flash("🌈 Prompts recargados", SOFT_PURPLE)
        self.kawaii_log("Prompts recargados.")

    def kawaii_log(self, msg):
        self.logs.insert("end", msg + "\n")
        self.logs.see("end")

    def flash(self, msg, col):
        self.flash_label.configure(text=msg, text_color=col)
        self.after(2000, lambda: self.flash_label.configure(text=""))  # auto-oculta mensaje

    def test_log(self):
        self.kawaii_log("🧪 ¡Interface de prueba funcionando!")
        self.flash("¡Test GUI listo!", "#a3ffb1")

    def test_voice(self):
        self.kawaii_log("🎤 Prueba de Voz (dilo en alta!)")
        try:
            speak("Esto es una prueba de voz de tu IA VTuber.")
            self.flash("¡Voz generada con éxito!", "#aaffee")
        except Exception as e:
            self.kawaii_log(str(e))
            self.flash("❌ Error en la voz", "#ff8383")

    def test_ia(self):
        self.kawaii_log("🤖 Consultando IA...")
        try:
            respuesta = ask_groq("¿Quién eres?")
            self.kawaii_log("IA → " + respuesta)
            self.flash("¡Respuesta IA recibida!", SOFT_CYAN)
        except Exception as e:
            self.kawaii_log(str(e))
            self.flash("❌ Error con la IA", "#ff8889")

    def connect_twitch(self):
        self.kawaii_log("💬 Conectando Twitch...")
        try:
            start_chat(config)
            self.flash("¡Twitch conectado!", VIBRANT_PINK)
        except Exception as e:
            self.kawaii_log(str(e))
            self.flash("❌ Error con Twitch", "#ff8889")

    def ptt_click(self):
        self.kawaii_log("🔊 ¡Listo para hablar con tu IA en modo VTuber! (PTT)")
        # Aquí puedes llamar a PTTManager o lógica de voz

if __name__ == "__main__":
    app = App()
    app.mainloop()