"""
OCR usando EasyOCR - Offline, sin API keys
"""
import io
import traceback
import threading
import numpy as np

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

# Intentar importar EasyOCR
try:
    import easyocr
    EASYOCR_OK = True
except ImportError:
    EASYOCR_OK = False
    print("ADVERTENCIA: Instala EasyOCR: pip install easyocr")


# Instancia global del OCR (se inicializa lazily)
# Instancias globales
_ocr_readers = {}
_ocr_lock = threading.Lock()
_ultimo_hash = None

# Solo ['en','ja'] es rapido y cubre ~95% de juegos
LECTORES_POR_DEFECTO = [['en', 'ja']]
LECTORES_COMPLETOS = [['en', 'ja'], ['en', 'ko'], ['en', 'ch_sim']]


def _get_ocr_reader(languages):
    """Obtiene o crea un reader para un grupo de idiomas"""
    key = tuple(sorted(languages))
    if key in _ocr_readers:
        return _ocr_readers[key]
    
    with _ocr_lock:
        if key not in _ocr_readers and EASYOCR_OK:
            try:
                reader = easyocr.Reader(
                    list(languages),
                    gpu=False,
                    verbose=False
                )
                _ocr_readers[key] = reader
            except Exception as e:
                print(f"[ERROR] Error creando reader {languages}: {e}")
                return None
        return _ocr_readers.get(key)


def _detectar_idiomas_imagen(img_np):
    """Detecta qué idiomas hay en la imagen para elegir lectores"""
    # Muestrear pixeles para detectar rangos Unicode
    flat = img_np.reshape(-1)
    # No podemos detectar idiomas solo de pixeles, usar todos los lectores
    return None


def _pil_to_numpy(img):
    """Convierte PIL Image a numpy array para EasyOCR"""
    if img is None:
        return None
    try:
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        return np.array(img)
    except Exception as e:
        print(f"[ERROR] Error convirtiendo imagen: {e}")
        return None


def capturar_pantalla(bbox=None, reducir=True):
    """Captura la pantalla y retorna imagen PIL reducida para OCR rapido"""
    if not PIL_OK:
        return None
    try:
        from PIL import ImageGrab
        if bbox:
            img = ImageGrab.grab(bbox=bbox)
        else:
            img = ImageGrab.grab()
        # Reducir para OCR mas rapido (960p es suficiente)
        if reducir and img.size[0] > 960:
            w, h = img.size
            ratio = 960 / w
            img = img.resize((960, int(h * ratio)), Image.LANCZOS)
        return img
    except Exception as e:
        print(f"[ERROR] Error capturando: {e}")
        return None


def reconocer_texto(img):
    """
    Reconoce texto de una imagen PIL usando EasyOCR (multi-idioma).
    """
    if not EASYOCR_OK:
        print("[ERROR] EasyOCR no disponible")
        return None, "EasyOCR no disponible"
    
    try:
        if img is None:
            print("[ERROR] Imagen es None")
            return None, "Imagen nula"
        
        if isinstance(img, np.ndarray):
            img_np = img
        else:
            img_np = _pil_to_numpy(img)
            if img_np is None:
                print("[ERROR] Error convirtiendo imagen")
                return None, "Error convirtiendo imagen"
        
        # Ejecutar OCR con múltiples lectores de idiomas
        grupos = [['en', 'ja'], ['en', 'ko'], ['en', 'ch_sim']]
        todos = {}
        
        for grupo in grupos:
            reader = _get_ocr_reader(grupo)
            if reader is None:
                continue
            
            result = reader.readtext(img_np)
            if result:
                for item in result:
                    texto = item[1]
                    conf = item[2]
                    if texto and texto.strip() and conf > 0.3:
                        key = texto.strip().lower()
                        if key not in todos or todos[key][2] < conf:
                            todos[key] = item
        
        if not todos:
            return "", "success"
        
        textos = [v[1].strip() for v in todos.values()]
        texto_completo = " ".join(textos)
        return texto_completo.strip(), "success"
        
    except Exception as e:
        print(f"[ERROR] OCR error: {e}")
        import traceback
        traceback.print_exc()
        return None, str(e)


def reconocer_texto_con_posicion(img, usar_todos_idiomas=False):
    """
    Reconoce texto con posición (bounding boxes).
    Por defecto usa solo ['en','ja'] (mas rapido).
    Si usar_todos_idiomas=True, incluye coreano y chino (mas lento).
    Retorna lista de diccionarios con texto, posición y confianza.
    """
    if not EASYOCR_OK:
        return []
    
    try:
        img_np = _pil_to_numpy(img)
        if img_np is None:
            print("[ERROR] OCR: error convirtiendo imagen")
            return []
        
        w, h = img.size if img else (1920, 1080)
        
        # Seleccionar grupos de idiomas
        if usar_todos_idiomas:
            grupos = LECTORES_COMPLETOS
        else:
            grupos = LECTORES_POR_DEFECTO
        
        todos_resultados = {}
        
        for grupo in grupos:
            reader = _get_ocr_reader(grupo)
            if reader is None:
                continue
            
            results = reader.readtext(img_np)
            
            if results:
                for item in results:
                    texto = item[1]
                    conf = item[2]
                    if texto and texto.strip() and conf > 0.3:
                        key = texto.strip().lower()
                        if key not in todos_resultados or todos_resultados[key][2] < conf:
                            todos_resultados[key] = item
                
                # Si encontramos suficiente texto con el primer lector, salir
                if len(todos_resultados) >= 3 and grupo == ['en', 'ja']:
                    break
        
        if not todos_resultados:
            return []
        
        bloques = []
        for key, item in todos_resultados.items():
            box = item[0]
            texto = item[1].strip()
            conf = item[2]
            
            if isinstance(box, list) and len(box) >= 4:
                xs = [p[0] for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                ys = [p[1] for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                
                if not xs or not ys:
                    continue
                
                cx = (min(xs) + max(xs)) / 2
                cy = (min(ys) + max(ys)) / 2
                bw = max(xs) - min(xs)
                bh = max(ys) - min(ys)
                
                bloques.append({
                    'original': texto,
                    'traduccion': '',
                    'x_pct': cx / w if w > 0 else 0.5,
                    'y_pct': cy / h if h > 0 else 0.5,
                    'width_pct': bw / w if w > 0 else 0.1,
                    'height_pct': bh / h if h > 0 else 0.1,
                    'confianza': conf,
                })
        
        return bloques
        
    except Exception as e:
        import traceback
        print(f"[ERROR] OCR: {e}")
        return []
    
    try:
        print("[DEBUG] OCR: convirtiendo imagen...")
        img_np = _pil_to_numpy(img)
        if img_np is None:
            print("[ERROR] OCR: error convirtiendo imagen")
            return []
        
        w, h = img.size if img else (1920, 1080)
        
        # Idiomas a probar (cada grupo requiere inglés)
        grupos_idiomas = [['en', 'ja'], ['en', 'ko'], ['en', 'ch_sim']]
        
        todos_resultados = {}
        
        for grupo in grupos_idiomas:
            reader = _get_ocr_reader(grupo)
            if reader is None:
                continue
            
            print(f"[DEBUG] OCR: readtext con {grupo}...")
            results = reader.readtext(img_np)
            
            if results:
                print(f"[DEBUG] OCR: {grupo} -> {len(results)} items")
                for item in results:
                    texto = item[1]
                    conf = item[2]
                    if texto and texto.strip() and conf > 0.3:
                        # Usar texto como key para deduplicar
                        key = texto.strip().lower()
                        if key not in todos_resultados or todos_resultados[key][2] < conf:
                            todos_resultados[key] = item
            else:
                print(f"[DEBUG] OCR: {grupo} -> 0 items")
        
        if not todos_resultados:
            print("[DEBUG] OCR: sin resultados de ningun lector")
            return []
        
        print(f"[DEBUG] OCR: total {len(todos_resultados)} items unicos")
        
        bloques = []
        for key, item in todos_resultados.items():
            box = item[0]
            texto = item[1].strip()
            conf = item[2]
            
            if isinstance(box, list) and len(box) >= 4:
                xs = [p[0] for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                ys = [p[1] for p in box if isinstance(p, (list, tuple)) and len(p) >= 2]
                
                if not xs or not ys:
                    continue
                
                cx = (min(xs) + max(xs)) / 2
                cy = (min(ys) + max(ys)) / 2
                bw = max(xs) - min(xs)
                bh = max(ys) - min(ys)
                
                bloques.append({
                    'original': texto,
                    'traduccion': '',
                    'x_pct': cx / w if w > 0 else 0.5,
                    'y_pct': cy / h if h > 0 else 0.5,
                    'width_pct': bw / w if w > 0 else 0.1,
                    'height_pct': bh / h if h > 0 else 0.1,
                    'confianza': conf,
                })
        
        return bloques
        
    except Exception as e:
        import traceback
        print(f"[ERROR] OCR: {e}")
        print(f"Trace: {traceback.format_exc()}")
        return []


def ocr_pantalla(bbox=None):
    """
    Captura pantalla y retorna texto reconocido.
    Función principal simple.
    """
    if not PIL_OK:
        return None, "Falta pillow"
    if not EASYOCR_OK:
        return None, "Falta EasyOCR (pip install easyocr)"
    
    img = capturar_pantalla(bbox)
    if img is None:
        return None, "Error capturando"
    
    texto, estado = reconocer_texto(img)
    return texto, estado


# Alias para compatibilidad
obtener_texto_desde_pantalla = ocr_pantalla
reconocimiento_texto_simple = ocr_pantalla