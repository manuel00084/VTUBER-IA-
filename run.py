"""
Karin VTuber - Launcher
"""
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

print("Starting Karin VTuber...")
print(f"Current directory: {os.getcwd()}")
print(f"APP_DIR: {APP_DIR}")

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