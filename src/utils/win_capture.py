"""
Captura de pantalla - dxcam > GDI > mss
"""
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


