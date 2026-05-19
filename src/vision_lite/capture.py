import time
import numpy as np
from threading import Lock

try:
    import dxcam
    DXCAM_OK = True
except ImportError:
    DXCAM_OK = False

try:
    from PIL import ImageGrab
    PILGRAB_OK = True
except ImportError:
    PILGRAB_OK = False

import cv2


class ScreenCapture:
    def __init__(self, target_fps=30, region=None, output_color="BGR"):
        self._camera = None
        self._lock = Lock()
        self._target_fps = target_fps
        self._region = region
        self._output_color = output_color
        self._last_grab = 0

        if DXCAM_OK:
            try:
                self._camera = dxcam.create(output_color=output_color)
            except Exception:
                self._camera = None

    def grab(self):
        with self._lock:
            min_interval = 1.0 / max(self._target_fps, 1)
            now = time.time()
            if now - self._last_grab < min_interval:
                return None

            if self._camera is not None:
                frame = self._camera.grab(region=self._region)
                if frame is not None:
                    self._last_grab = now
                    return frame

            if PILGRAB_OK:
                bbox = self._region if self._region else None
                pil_img = ImageGrab.grab(bbox=bbox, all_screens=True)
                if pil_img:
                    self._last_grab = now
                    if self._output_color.upper() == "BGR":
                        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                    return np.array(pil_img)
            return None

    def stop_capture(self):
        with self._lock:
            if self._camera is not None:
                try:
                    if hasattr(self._camera, 'stop') and self._camera.is_capturing:
                        self._camera.stop()
                except Exception:
                    pass

    def release(self):
        self.stop_capture()
        if self._camera is not None:
            try:
                del self._camera
            except Exception:
                pass
            self._camera = None


