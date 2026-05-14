from .ptt import PTTManager
from .game_watcher import GameWatcher

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False