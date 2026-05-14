"""
game_events.py — Detección mejorada de eventos en juegos
Usa OpenCV para detección de eventos, colores y análisis de imagen
"""
import cv2
import numpy as np
import threading, time
from collections import deque
import re

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PAL_OK = False

from src.utils.win_capture import capturar_pantalla


def _preprocesar_imagen(img):
    """
    Preprocesa la imagen para mejorar OCR y detección.
    Returns: imagen preprocesada (numpy array)
    """
    if img is None:
        return None
    
    try:
        if hasattr(img, 'convert'):
            img = np.array(img)
        
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gray = img
        
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        return enhanced
    except:
        return img


def _comparar_frames(img1, img2, threshold=0.95):
    """
    Compara dos imágenes y retorna el porcentaje de diferencia.
    """
    if img1 is None or img2 is None:
        return 0
    
    try:
        if hasattr(img1, 'convert'):
            img1 = np.array(img1)
        if hasattr(img2, 'convert'):
            img2 = np.array(img2)
        
        if len(img1.shape) == 3:
            gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)
        else:
            gray1 = img1
            
        if len(img2.shape) == 3:
            gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)
        else:
            gray2 = img2
        
        gray1 = cv2.resize(gray1, (320, 180))
        gray2 = cv2.resize(gray2, (320, 180))
        
        diff = cv2.absdiff(gray1, gray2)
        non_zero = cv2.countNonZero(diff)
        total_pixels = diff.size
        cambio = 1 - (non_zero / total_pixels)
        
        return cambio
    except:
        return 0


def _detectar_colores_mejorado(img):
    """
    Detección mejorada de colores para eventos de juego.
    Returns: dict con colores relevantes y nivel de detección
    """
    if img is None:
        return {}
    
    try:
        if hasattr(img, 'convert'):
            img_array = np.array(img)
        else:
            img_array = img
        
        hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
        
        colores = {}
        
        bajo_rojo1 = np.array([0, 120, 120])
        alto_rojo1 = np.array([10, 255, 255])
        bajo_rojo2 = np.array([170, 120, 120])
        alto_rojo2 = np.array([180, 255, 255])
        mask_rojo = cv2.inRange(hsv, bajo_rojo1, alto_rojo1) + cv2.inRange(hsv, bajo_rojo2, alto_rojo2)
        colores["rojo"] = cv2.countNonZero(mask_rojo)
        
        bajo_naranja = np.array([10, 150, 150])
        alto_naranja = np.array([25, 255, 255])
        mask_naranja = cv2.inRange(hsv, bajo_naranja, alto_naranja)
        colores["naranja"] = cv2.countNonZero(mask_naranja)
        
        bajo_amarillo = np.array([25, 150, 150])
        alto_amarillo = np.array([35, 255, 255])
        mask_amarillo = cv2.inRange(hsv, bajo_amarillo, alto_amarillo)
        colores["amarillo"] = cv2.countNonZero(mask_amarillo)
        
        bajo_verde1 = np.array([40, 80, 80])
        alto_verde1 = np.array([70, 255, 255])
        mask_verde = cv2.inRange(hsv, bajo_verde1, alto_verde1)
        colores["verde"] = cv2.countNonZero(mask_verde)
        
        bajo_azul = np.array([100, 100, 100])
        alto_azul = np.array([130, 255, 255])
        mask_azul = cv2.inRange(hsv, bajo_azul, alto_azul)
        colores["azul"] = cv2.countNonZero(mask_azul)
        
        bajo_morado = np.array([130, 80, 80])
        alto_morado = np.array([170, 255, 255])
        mask_morado = cv2.inRange(hsv, bajo_morado, alto_morado)
        colores["morado"] = cv2.countNonZero(mask_morado)
        
        bajo_dorado = np.array([15, 150, 150])
        alto_dorado = np.array([50, 255, 255])
        mask_dorado = cv2.inRange(hsv, bajo_dorado, alto_dorado)
        colores["dorado"] = cv2.countNonZero(mask_dorado)
        
        return colores
    except:
        return {}


def _detectar_barras(img):
    """
    Detecta barras de vida/mana/energía en la imagen.
    Returns: dict con info de barras
    """
    if img is None:
        return {}
    
    try:
        if hasattr(img, 'convert'):
            img_array = np.array(img)
        else:
            img_array = img
        
        h, w = img_array.shape[:2]
        
        barras = {
            "salud": 0,
            "mana": 0,
            "energia": 0,
            "experiencia": 0
        }
        
        roi_superior = img_array[0:int(h*0.15), :]
        hsv = cv2.cvtColor(roi_superior, cv2.COLOR_RGB2HSV)
        
        mask_rojo = cv2.inRange(hsv, np.array([0, 120, 120]), np.array([10, 255, 255])) + \
                    cv2.inRange(hsv, np.array([170, 120, 120]), np.array([180, 255, 255]))
        barras["salud"] = cv2.countNonZero(mask_rojo)
        
        mask_azul = cv2.inRange(hsv, np.array([100, 100, 100]), np.array([130, 255, 255]))
        barras["mana"] = cv2.countNonZero(mask_azul)
        
        mask_amarillo = cv2.inRange(hsv, np.array([25, 150, 150]), np.array([35, 255, 255]))
        barras["experiencia"] = cv2.countNonZero(mask_amarillo)
        
        return barras
    except:
        return {}


def _detectar_eventos_por_region(img):
    """
    Detecta eventos en regiones específicas de la pantalla.
    """
    if img is None:
        return []
    
    eventos = []
    
    try:
        if hasattr(img, 'convert'):
            img_array = np.array(img)
        else:
            img_array = img
        
        h, w = img_array.shape[:2]
        
        centro = img_array[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7)]
        
        hsv_centro = cv2.cvtColor(centro, cv2.COLOR_RGB2HSV)
        
        rojo_centro = cv2.inRange(hsv_centro, np.array([0, 120, 120]), np.array([10, 255, 255])) + \
                      cv2.inRange(hsv_centro, np.array([170, 120, 120]), np.array([180, 255, 255]))
        
        if cv2.countNonZero(rojo_centro) > 500:
            eventos.append("combate_centro")
        
        roi_inferior = img_array[int(h*0.8):, :]
        hsv_inferior = cv2.cvtColor(roi_inferior, cv2.COLOR_RGB2HSV)
        
        dorado_inferior = cv2.inRange(hsv_inferior, np.array([15, 150, 150]), np.array([50, 255, 255]))
        if cv2.countNonZero(dorado_inferior) > 300:
            eventos.append("loot_inventario")
        
        return eventos
    except:
        return []


def _detectar_cambio_significativo(img_actual, img_anterior, umbral=0.03):
    """
    Detecta si hay un cambio significativo entre frames.
    """
    cambio = _comparar_frames(img_actual, img_anterior)
    return cambio < (1 - umbral), cambio


class EventDetector:
    def __init__(self, intervalo_check=5):
        self.intervalo = intervalo_check
        self.ultimo_frame = None
        self.ultimo_evento = None
        self.historial_eventos = deque(maxlen=15)
        self._frame_anterior = None
        self._frame_previo_mov = None
        self._contador_ciclos = 0
        self._ultimo_estado = "normal"
        self._contador_estado = 0
    
    def detectar(self, img_actual):
        """
        Detecta el evento actual basándose en múltiples análisis.
        Returns: (evento, detalle, confianza)
        """
        self._contador_ciclos += 1
        
        cambio_significativo, valor_cambio = _detectar_cambio_significativo(
            img_actual, self._frame_anterior
        )
        
        colores = _detectar_colores_mejorado(img_actual)
        barras = _detectar_barras(img_actual)
        eventos_region = _detectar_eventos_por_region(img_actual)
        
        evento = None
        detalle = None
        confianza = 0
        
        if eventos_region:
            if "combate_centro" in eventos_region:
                evento = "combate"
                detalle = "enemigo detectado en centro de pantalla"
                confianza = 0.8
            elif "loot_inventario" in eventos_region:
                evento = "loot"
                detalle = "objeto detectado en inventario"
                confianza = 0.6
        
        if not evento:
            if colores.get("rojo", 0) > 8000:
                evento = "combate"
                detalle = "mucho rojo en pantalla - combate activo"
                confianza = 0.75
            elif colores.get("naranja", 0) > 5000:
                evento = "advertencia"
                detalle = "advertencia naranja detectada"
                confianza = 0.6
            elif colores.get("dorado", 0) > 4000:
                evento = "loot"
                detalle = "objeto dorado/loot detectado"
                confianza = 0.6
            elif colores.get("verde", 0) > 10000 and colores.get("rojo", 0) < 3000:
                evento = "explorando"
                detalle = "mucho verde - explorando/zona segura"
                confianza = 0.5
            elif colores.get("amarillo", 0) > 5000:
                evento = "objetivo"
                detalle = "marcador amarillo - objetivo activo"
                confianza = 0.5
        
        if cambio_significativo and valor_cambio < 0.4:
            if evento is None:
                evento = "cambio_escena"
                detalle = "cambio significativo de pantalla"
                confianza = 0.85
            else:
                evento = evento + "_cambio"
                confianza = min(confianza + 0.1, 0.95)
        
        if cambio_significativo and 0.4 <= valor_cambio < 0.8:
            if evento is None:
                evento = "accion"
                detalle = "alguna acción en pantalla"
                confianza = 0.5
        
        if barras.get("salud", 0) > 2000 and evento != "combate":
            if self._ultimo_estado != "combate":
                detalle = (detalle or "") + " [barras detectadas]"
        
        if evento:
            self.historial_eventos.append(evento)
        
        mov = {}
        if self._frame_previo_mov is not None:
            mov = _detectar_movimiento(img_actual, self._frame_previo_mov)
        
        self._frame_previo_mov = img_actual
        self._frame_anterior = img_actual
        self.ultimo_evento = evento
        
        return evento, detalle, confianza, mov
    
    def get_estado(self):
        """Retorna el estado actual basado en el historial"""
        if not self.historial_eventos:
            return "normal"
        
        ultimos = list(self.historial_eventos)[-5:]
        
        conteo = {}
        for e in ultimos:
            e_base = e.replace("_cambio", "").replace("_detected", "")
            conteo[e_base] = conteo.get(e_base, 0) + 1
        
        if conteo.get("combate", 0) >= 2:
            return "en_combate"
        elif conteo.get("loot", 0) >= 1:
            return "looteando"
        elif conteo.get("cambio_escena", 0) >= 1:
            return "cambiando_escena"
        elif conteo.get("explorando", 0) >= 2:
            return "explorando"
        
        return ultimos[-1] if ultimos[-1] else "normal"


def crear_detector():
    """Crea una instancia del detector de eventos"""
    return EventDetector()


def _detectar_colores_dominantes(img):
    """Alias para compatibilidad"""
    return _detectar_colores_mejorado(img)


def _detectar_entidades(img):
    """
    Detecta entidades (personajes, enemigos) en la imagen usando análisis de contornos.
    Returns: dict con info de entidades detectadas
    """
    if img is None:
        return {}
    
    try:
        if hasattr(img, 'convert'):
            img_array = np.array(img)
        else:
            img_array = img
        
        h, w = img_array.shape[:2]
        
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        entidades = {"personajes": [], "enemigos": [], "cantidad": 0}
        altura_promedio = h // 10
        
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            
            if ch < 30 or cw < 20:
                continue
            if ch > altura_promedio * 5:
                continue
            
            area = cw * ch
            if area < 800 or area > (w * h * 0.25):
                continue
            
            proporcion = ch / cw if cw > 0 else 0
            if proporcion < 1.2:
                continue
            
            roi = img_array[y:y+ch, x:x+cw]
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
            
            area_roi = cw * ch
            rojo_cnt = cv2.countNonZero(cv2.inRange(hsv_roi, np.array([0, 80, 80]), np.array([15, 255, 255])))
            azul_cnt = cv2.countNonZero(cv2.inRange(hsv_roi, np.array([90, 40, 40]), np.array([140, 255, 255])))
            verde_cnt = cv2.countNonZero(cv2.inRange(hsv_roi, np.array([35, 40, 40]), np.array([75, 255, 255])))
            oscuro_cnt = cv2.countNonZero(cv2.inRange(hsv_roi, np.array([0, 0, 0]), np.array([180, 255, 40])))
            
            if rojo_cnt > area_roi * 0.08:
                entidades["enemigos"].append({"tipo": "enemigo_rojo", "x": round(x/w, 2), "y": round(y/h, 2)})
            elif oscuro_cnt > area_roi * 0.25:
                entidades["personajes"].append({"tipo": "pj_oscuro", "x": round(x/w, 2), "y": round(y/h, 2)})
            elif verde_cnt > area_roi * 0.12:
                entidades["personajes"].append({"tipo": "pj_verde", "x": round(x/w, 2), "y": round(y/h, 2)})
            elif azul_cnt > area_roi * 0.1:
                entidades["personajes"].append({"tipo": "aliado_azul", "x": round(x/w, 2), "y": round(y/h, 2)})
            else:
                entidades["personajes"].append({"tipo": "pj_neutral", "x": round(x/w, 2), "y": round(y/h, 2)})
        
        entidades["cantidad"] = len(entidades["personajes"]) + len(entidades["enemigos"])
        
        return entidades
    
    except Exception as e:
        return {}


def _detectar_entorno(img):
    """
    Detecta el tipo de entorno/paisaje basándose en análisis de color.
    Returns: dict con info del entorno
    """
    if img is None:
        return {}
    
    try:
        if hasattr(img, 'convert'):
            img_array = np.array(img)
        else:
            img_array = img
        
        h, w = img_array.shape[:2]
        
        roi_inferior = img_array[int(h*0.6):, :]
        roi_superior = img_array[:int(h*0.4), :]
        
        hsv_inf = cv2.cvtColor(roi_inferior, cv2.COLOR_RGB2HSV)
        hsv_sup = cv2.cvtColor(roi_superior, cv2.COLOR_RGB2HSV)
        
        total = roi_inferior.shape[0] * roi_inferior.shape[1]
        
        verde = cv2.countNonZero(cv2.inRange(hsv_inf, np.array([30, 25, 25]), np.array([85, 255, 180]))) / total
        azul = cv2.countNonZero(cv2.inRange(hsv_sup, np.array([85, 25, 70]), np.array([135, 255, 255]))) / total
        cafe = cv2.countNonZero(cv2.inRange(hsv_inf, np.array([8, 25, 25]), np.array([35, 255, 140]))) / total
        gris = cv2.countNonZero(cv2.inRange(hsv_inf, np.array([0, 0, 40]), np.array([180, 40, 140]))) / total
        negro = cv2.countNonZero(cv2.inRange(hsv_inf, np.array([0, 0, 0]), np.array([180, 255, 45]))) / total
        
        entorno = {"tipo": "interior", "es_exterior": False, "colores": []}
        
        if verde > 0.18:
            entorno = {"tipo": "bosque/naturaleza", "es_exterior": True, "colores": ["verde", "marron"]}
        elif azul > 0.12:
            entorno = {"tipo": "exterior/ciudad", "es_exterior": True, "colores": ["azul", "blanco"]}
        elif negro > 0.35:
            entorno = {"tipo": "dungeon/cave", "es_exterior": False, "colores": ["negro", "gris"]}
        elif cafe > 0.22:
            entorno = {"tipo": "desierto/sabana", "es_exterior": True, "colores": ["marron", "arena"]}
        elif gris > 0.25:
            entorno = {"tipo": "ciudad/edificio", "es_exterior": False, "colores": ["gris", "concreto"]}
        
        gray = cv2.cvtColor(roi_inferior, cv2.COLOR_RGB2GRAY)
        entorno["brillo"] = int(np.mean(gray))
        
        return entorno
    
    except Exception as e:
        return {}


_ANALISIS_MAX_W = 640

def _reducir_si(img, max_w=640):
    """Reduce imagen para análisis si excede max_w"""
    if img is None:
        return img
    w = img.shape[1] if hasattr(img, 'shape') else (img.size[0] if hasattr(img, 'size') else 0)
    if w > max_w:
        ratio = max_w / w
        h = int((img.shape[0] if hasattr(img, 'shape') else img.size[1]) * ratio)
        return cv2.resize(img, (max_w, h), interpolation=cv2.INTER_LINEAR)
    return img

def _analisis_escena(img):
    """
    Análisis completo: entidades + entorno + colores + UI + movimiento.
    Returns: dict con toda la información
    """
    img = _reducir_si(img, _ANALISIS_MAX_W)
    entidades = _detectar_entidades(img)
    entorno = _detectar_entorno(img)
    colores = _detectar_colores_mejorado(img)
    ui = _detectar_ui(img)
    textura = _analizar_textura(img)
    
    return {
        "entidades": entidades,
        "entorno": entorno,
        "colores": colores,
        "ui": ui,
        "textura": textura
    }


def _detectar_ui(img):
    """
    Detecta elementos de UI del juego (barras, minimapa, menús).
    Returns: dict con info de UI detectada
    """
    if img is None:
        return {}
    
    try:
        if hasattr(img, 'convert'):
            img_array = np.array(img)
        else:
            img_array = img
        
        h, w = img_array.shape[:2]
        
        ui_elements = {
            "barras": [],
            "minimap": False,
            "menus": False,
            "iconos": []
        }
        
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        roi_esquina_sup_der = img_array[:int(h*0.25), int(w*0.75):]
        if roi_esquina_sup_der.size > 0:
            hsv_minimap = cv2.cvtColor(roi_esquina_sup_der, cv2.COLOR_RGB2HSV)
            verde_minimap = cv2.countNonZero(cv2.inRange(hsv_minimap, np.array([60, 50, 50]), np.array([90, 255, 200])))
            if verde_minimap > roi_esquina_sup_der.shape[0] * roi_esquina_sup_der.shape[1] * 0.05:
                ui_elements["minimap"] = True
        
        roi_barras_sup = img_array[:int(h*0.08), :]
        if roi_barras_sup.size > 0:
            hsv_barras = cv2.cvtColor(roi_barras_sup, cv2.COLOR_RGB2HSV)
            
            rojo_barra = cv2.countNonZero(cv2.inRange(hsv_barras, np.array([0, 100, 100]), np.array([10, 255, 255])))
            if rojo_barra > 500:
                ui_elements["barras"].append("salud")
            
            azul_barra = cv2.countNonZero(cv2.inRange(hsv_barras, np.array([100, 80, 80]), np.array([130, 255, 255])))
            if azul_barra > 500:
                ui_elements["barras"].append("mana")
            
            amarillo_barra = cv2.countNonZero(cv2.inRange(hsv_barras, np.array([25, 100, 100]), np.array([35, 255, 255])))
            if amarillo_barra > 500:
                ui_elements["barras"].append("experiencia")
        
        roi_bordes = np.concatenate([
            img_array[:int(h*0.02), :].flatten(0),
            img_array[int(h*0.98):, :].flatten(0),
            img_array[:, :int(w*0.02)].flatten(0),
            img_array[:, int(w*0.98):].flatten(0)
        ])
        
        if len(roi_bordes) > 0:
            bordes_claros = np.sum(roi_bordes > 200)
            if bordes_claros > len(roi_bordes) * 0.3:
                ui_elements["menus"] = True
        
        return ui_elements
    
    except Exception as e:
        return {}


def _analizar_textura(img):
    """
    Analiza la textura de la imagen para mejor clasificación del entorno.
    Returns: dict con info de textura
    """
    if img is None:
        return {}
    
    try:
        if hasattr(img, 'convert'):
            img_array = np.array(img)
        else:
            img_array = img
        
        h, w = img_array.shape[:2]
        
        roi_central = img_array[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7)]
        gray = cv2.cvtColor(roi_central, cv2.COLOR_RGB2GRAY)
        
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        varianza = np.var(laplacian)
        
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)
        magnitud = np.sqrt(sobelx**2 + sobely**2)
        bordes_promedio = np.mean(magnitud)
        
        textura = {
            "varianza_laplacian": float(varianza),
            "bordes_promedio": float(bordes_promedio),
            "tipo": "desconocido"
        }
        
        if varianza < 500:
            textura["tipo"] = "liso/plano"
        elif varianza < 2000:
            textura["tipo"] = "moderado"
        else:
            textura["tipo"] = "detallado/complejo"
        
        if bordes_promedio < 20:
            textura["tipo"] += " - uniforme"
        elif bordes_promedio > 60:
            textura["tipo"] += " - caotico"
        
        return textura
    
    except Exception as e:
        return {}


def _detectar_movimiento(img_actual, img_anterior):
    """
    Detecta movimiento entre dos frames.
    Returns: dict con info de movimiento
    """
    if img_actual is None or img_anterior is None:
        return {"hay_movimiento": False, "intensidad": 0, "direccion": "ninguna"}
    
    try:
        if hasattr(img_actual, 'convert'):
            img1 = np.array(img_actual)
            img2 = np.array(img_anterior)
        else:
            img1 = img_actual
            img2 = img_anterior
        
        gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)
        
        gray1 = cv2.resize(gray1, (160, 90))
        gray2 = cv2.resize(gray2, (160, 90))
        
        diff = cv2.absdiff(gray1, gray2)
        
        non_zero = cv2.countNonZero(diff)
        total = diff.size
        porcentaje_mov = non_zero / total
        
        movimiento = {
            "hay_movimiento": porcentaje_mov > 0.05,
            "intensidad": round(porcentaje_mov * 100, 1),
            "direccion": "ninguna"
        }
        
        if porcentaje_mov > 0.05:
            h, w = diff.shape
            
            mitad_izq = diff[:, :w//2]
            mitad_der = diff[:, w//2:]
            mitad_sup = diff[:h//2, :]
            mitad_inf = diff[h//2:, :]
            
            movimiento_izq = np.sum(mitad_izq)
            movimiento_der = np.sum(mitad_der)
            movimiento_sup = np.sum(mitad_sup)
            movimiento_inf = np.sum(mitad_inf)
            
            if movimiento_der > movimiento_izq * 1.3:
                movimiento["direccion"] = "derecha"
            elif movimiento_izq > movimiento_der * 1.3:
                movimiento["direccion"] = "izquierda"
            elif movimiento_inf > movimiento_sup * 1.3:
                movimiento["direccion"] = "abajo"
            elif movimiento_sup > movimiento_inf * 1.3:
                movimiento["direccion"] = "arriba"
        
        return movimiento
    
    except Exception as e:
        return {"hay_movimiento": False, "intensidad": 0, "direccion": "ninguna"}