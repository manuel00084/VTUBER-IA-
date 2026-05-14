"""
Karin VTuber - Launcher
"""
import os
import sys
import glob

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if hasattr(sys, '_MEIPASS'):
    APP_DIR = sys._MEIPASS
    
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

print("Starting Karin VTuber...")
print(f"Current directory: {os.getcwd()}")
print(f"APP_DIR: {APP_DIR}")

# Buscar vosk en el directorio temporal o en el path
vosk_paths = [
    os.path.join(APP_DIR, 'vosk'),
    os.path.join(os.getcwd(), 'vosk'),
]
for vp in vosk_paths:
    if os.path.exists(vp):
        sys.path.insert(0, os.path.dirname(vp))
        break

try:
    print("Importing App from src.ui.main...")
    from src.ui.main import App
    print("Import successful!")
except Exception as e:
    print(f"Failed to import App: {e}")
    import traceback
    traceback.print_exc()
    input("\nPresiona ENTER para cerrar...")
    sys.exit(1)

if __name__ == "__main__":
    try:
        print("Creating App instance...")
        app = App()
        print("App instance created, starting mainloop...")
        app.mainloop()
    except Exception as e:
        print(f"\n========== ERROR AL INICIAR ==========")
        import traceback
        traceback.print_exc()
        print("======================================")
        input("\nPresiona ENTER para cerrar...")