"""
windows_ocr.py - Versión corregida y optimizada (solo winocr nativo)
"""

from PIL import Image
import numpy as np

try:
    from winocr import recognize_pil_sync
    WINOCR_DISPONIBLE = True
except ImportError:
    WINOCR_DISPONIBLE = False
    print("❌ winocr no instalado. Ejecuta: pip install winocr")


def capturar_pantalla(bbox=None):
    """Captura de pantalla (completa o área específica)"""
    try:
        from PIL import ImageGrab
        if bbox:
            screenshot = ImageGrab.grab(bbox=bbox)
        else:
            screenshot = ImageGrab.grab()

        # Reducir resolución para más velocidad
        if screenshot.width > 1400:
            ratio = 1400 / screenshot.width
            new_size = (int(screenshot.width * ratio), int(screenshot.height * ratio))
            screenshot = screenshot.resize(new_size, Image.LANCZOS)

        return screenshot
    except Exception as e:
        print(f"Error captura pantalla: {e}")
        return None


def reconocer_texto_con_posicion(img):
    """
    OCR con Windows nativo + posición de bloques
    """
    if not WINOCR_DISPONIBLE:
        print("❌ winocr no disponible")
        return []

    if img is None:
        return []

    try:
        if isinstance(img, np.ndarray):
            img = Image.fromarray(img)

        result = recognize_pil_sync(img)   # ← Función correcta

        bloques = []
        width, height = img.size

        for line in result.get("lines", []):
            texto = line.get("text", "").strip()
            if len(texto) < 2:
                continue

            # Bounding box del line
            bbox = line.get("bounding_rect", {})
            x = bbox.get("x", 0)
            y = bbox.get("y", 0)
            w = bbox.get("width", 0)
            h = bbox.get("height", 0)

            bloques.append({
                'original': texto,
                'traduccion': '',
                'x_pct': (x + w/2) / width,
                'y_pct': (y + h/2) / height,
                'width_pct': w / width,
                'height_pct': h / height,
                'confianza': 0.85
            })

        return bloques

    except Exception as e:
        print(f"Error Windows OCR: {e}")
        return []


def reconocer_texto(img):
    """Versión simple solo texto"""
    bloques = reconocer_texto_con_posicion(img)
    texto = " | ".join(b['original'] for b in bloques)
    return texto, "ok" if bloques else "sin_texto"


# Alias para compatibilidad
ocr_pantalla = reconocer_texto