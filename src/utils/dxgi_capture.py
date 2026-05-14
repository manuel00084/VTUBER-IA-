"""
Captura de pantalla - dxcam > GDI > mss
Soporta región (bbox) para capturar solo un área.
"""
import sys
from typing import Optional

try:
    from PIL import Image
    import numpy as np
    PIL_OK = True
except ImportError:
    PIL_OK = False


_log_first = True

def _log(msg: str):
    global _log_first
    if _log_first:
        print(f"[CAPTURA] {msg}", file=sys.stderr)
        _log_first = False


def _recortar(img: Image.Image, region) -> Image.Image:
    """Recorta imagen a la región (left, top, right, bottom)"""
    if region and len(region) == 4:
        l, t, r, b = region
        w, h = img.size
        l = max(0, min(l, w))
        r = max(l, min(r, w))
        t = max(0, min(t, h))
        b = max(t, min(b, h))
        if r > l and b > t:
            img = img.crop((l, t, r, b))
    return img


# ===== DXCAM =====

try:
    import dxcam
    DXCAM_OK = True
    _camera = None
except ImportError:
    DXCAM_OK = False
    _camera = None


def _ensure_camera():
    global _camera
    if _camera is None and DXCAM_OK:
        try:
            _camera = dxcam.create(output_idx=0, output_color="RGB")
        except Exception as e:
            _log(f"dxcam create error: {e}")


MAX_CAPTURE_W = 800

def capture_dxgi(region=None) -> Optional[Image.Image]:
    if not PIL_OK or not DXCAM_OK:
        return None
    try:
        _ensure_camera()
        if _camera is None:
            return None
        frame = _camera.grab()
        if frame is None:
            return None
        img = Image.fromarray(frame)
        img = _recortar(img, region)
        if img.size[0] > MAX_CAPTURE_W:
            r = MAX_CAPTURE_W / img.size[0]
            img = img.resize((MAX_CAPTURE_W, int(img.size[1] * r)), Image.LANCZOS)
        return img
    except Exception as e:
        _log(f"dxcam error: {e}")
        return None


# ===== GDI =====

def capture_gdi(region=None) -> Optional[Image.Image]:
    if not PIL_OK:
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, sw, sh)
        gdi32.SelectObject(hdc_mem, hbmp)
        gdi32.BitBlt(hdc_mem, 0, 0, sw, sh, hdc_screen, 0, 0, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_ulong), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_short),
                ("biBitCount", ctypes.c_short), ("biCompression", ctypes.c_ulong),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize, bmi.biWidth = 40, sw
        bmi.biHeight, bmi.biPlanes = -sh, 1
        bmi.biBitCount = 32

        buffer = ctypes.create_string_buffer(sw * sh * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, sh, buffer, ctypes.byref(bmi), 0)

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        arr = np.frombuffer(buffer, dtype=np.uint8).reshape(sh, sw, 4)
        arr = arr[:, :, [2, 1, 0]]

        img = Image.fromarray(arr, 'RGB')
        img = _recortar(img, region)
        if img.size[0] > MAX_CAPTURE_W:
            r = MAX_CAPTURE_W / img.size[0]
            img = img.resize((MAX_CAPTURE_W, int(img.size[1] * r)), Image.LANCZOS)
        return img

    except:
        return None


# ===== MSS =====

def capture_mss(region=None) -> Optional[Image.Image]:
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
            arr = np.array(img)[..., [2, 1, 0]]
            pil = Image.fromarray(arr, 'RGB')
            pil = _recortar(pil, region)
            if pil.size[0] > 800:
                r = MAX_CAPTURE_W / pil.size[0]; pil = pil.resize((MAX_CAPTURE_W, int(pil.size[1] * r)), Image.LANCZOS)
            return pil
    except:
        return None


# ===== PRINCIPAL =====

def capturar_pantalla(region=None):
    """dxcam > GDI > mss — todas aceptan región"""
    img = capture_dxgi(region)
    if img is not None:
        return img
    img = capture_gdi(region)
    if img is not None:
        return img
    img = capture_mss(region)
    if img is not None:
        return img
    _log("ERROR: Sin metodo de captura")
    return None


if __name__ == "__main__":
    img = capturar_pantalla()
    print(f"Captura: {img.size if img else 'None'}")
