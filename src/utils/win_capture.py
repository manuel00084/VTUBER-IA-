"""
Windows Graphics Capture - Alternativas de captura de pantalla
"""
import io
import struct
import ctypes
import ctypes.wintypes as wintypes
from typing import Optional, Tuple

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False


# Constantes de Windows
DIB_RGB_COLORS = 0
BI_RGB = 0
SRCCOPY = 0x00CC0020
HWND_DESKTOP = 0

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BITMAPHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def _get_screen_size():
    """Obtiene el tamaño de la pantalla"""
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def capturar_pantalla_gdi(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """Captura usando GDI"""
    try:
        width, height = _get_screen_size()
        
        if region:
            x1, y1, x2, y2 = region
            width = x2 - x1
            height = y2 - y1
        else:
            x1, y1 = 0, 0
        
        hwnd = HWND_DESKTOP
        hwndDC = user32.GetWindowDC(hwnd)
        mfcDC = gdi32.CreateCompatibleDC()
        saveDC = mfcDC
        
        hBitmap = gdi32.CreateCompatibleBitmap(hwndDC, width, height)
        gdi32.SelectObject(mfcDC, hBitmap)
        gdi32.BitBlt(mfcDC, 0, 0, width, height, hwndDC, x1, y1, SRCCOPY)
        
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        
        buffer_size = width * height * 4
        buffer = ctypes.create_string_buffer(buffer_size)
        
        gdi32.GetDIBits(mfcDC, hBitmap, 0, height, buffer, ctypes.byref(bmi), DIB_RGB_COLORS)
        
        img = Image.frombuffer('RGBA', (width, height), buffer, 'raw', 'BGRA', 0, 1)
        
        gdi32.DeleteObject(hBitmap)
        gdi32.DeleteDC(mfcDC)
        user32.ReleaseDC(hwnd, hwndDC)
        
        return img
        
    except Exception as e:
        print(f"GDI error: {e}")
        return None


def capturar_pantalla_pil(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """Captura usando PIL (fallback)"""
    try:
        from PIL import ImageGrab
        if region:
            return ImageGrab.grab(bbox=region)
        return ImageGrab.grab()
    except Exception as e:
        print(f"PIL error: {e}")
        return None


def capturar_pantalla_mss(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """Captura usando mss (fallback)"""
    try:
        import mss
        import numpy as np
        
        with mss.mss() as sct:
            if region:
                monitor = {"top": region[1], "left": region[0], 
                         "width": region[2], "height": region[3]}
            else:
                monitor = sct.monitors[1]
            
            img = sct.grab(monitor)
            # mss returns BGRA, convert to RGBA for PIL
            arr = np.array(img)
            # Convert BGRA to RGBA
            arr = arr[..., [2, 1, 0, 3]]  # BGR -> RGB, keep A
            return Image.fromarray(arr, 'RGBA')
    except Exception as e:
        print(f"mss error: {e}")
        return None


def capturar_pantalla(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """
    Captura la pantalla - intenta GDI primero, luego PIL, luego mss
    """
    # Intentar GDI primero (más rápido para juegos)
    img = capturar_pantalla_gdi(region)
    if img is not None:
        return img
    
    # Fallback a PIL
    img = capturar_pantalla_pil(region)
    if img is not None:
        return img
    
    # Fallback final a mss
    return capturar_pantalla_mss(region)


def capturar_para_hash(region: Optional[Tuple[int, int, int, int]] = None) -> Tuple[Optional[Image.Image], str]:
    """Captura y retorna hash para detectar cambios"""
    import hashlib
    
    img = capturar_pantalla(region)
    
    if img is None:
        return None, ""
    
    img_small = img.resize((320, 180))
    buf = io.BytesIO()
    img_small.save(buf, format='JPEG', quality=50)
    img_hash = hashlib.md5(buf.getvalue()).hexdigest()
    
    return img, img_hash


def capturar_a_bytes(region: Optional[Tuple[int, int, int, int]] = None,
                    resize: Optional[Tuple[int, int]] = None,
                    quality: int = 70) -> Optional[bytes]:
    """Captura y retorna bytes JPEG"""
    img = capturar_pantalla(region)
    
    if img is None:
        return None
    
    if resize:
        img = img.resize(resize, Image.LANCZOS)
    
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    return buf.getvalue()