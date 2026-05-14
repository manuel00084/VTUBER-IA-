"""
Captura de pantalla - dxcam > GDI > mss
"""
import io
from typing import Optional

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False


def capturar_pantalla(region=None):
    """Captura pantalla: dxcam > GDI > mss (soporta región)"""
    if not PIL_OK:
        return None

    from src.utils.dxgi_capture import capturar_pantalla as capture
    return capture(region)


def capturar_para_hash(region=None):
    import hashlib
    img = capturar_pantalla(region)
    if img is None:
        return None, ""
    img_small = img.resize((64, 36), Image.LANCZOS)
    buf = io.BytesIO()
    img_small.save(buf, format='JPEG', quality=50)
    return img, hashlib.md5(buf.getvalue()).hexdigest()


def capturar_a_bytes(region=None, resize=None, quality=70):
    img = capturar_pantalla(region)
    if img is None:
        return None
    if resize:
        img = img.resize(resize, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    return buf.getvalue()