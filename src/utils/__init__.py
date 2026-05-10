from .ptt import PTTManager
from .translator import TranslatorManager, MODOS, MODO_DEFAULT
from .game_watcher import GameWatcher

try:
    from PIL import ImageGrab
    PIL_OK = True
except ImportError:
    PIL_OK = False