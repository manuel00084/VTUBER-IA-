"""
vision.py — Utilidades de visión: motion, color, templates, background subtraction
"""
import random, re
import cv2
import numpy as np


def detectar_movimiento(frame_actual, frame_anterior, umbral=0.03):
    if frame_anterior is None:
        return {"hay": False, "intensidad": 0, "direccion": "ninguna"}
    try:
        a = cv2.resize(frame_actual, (640, 360))
        b = cv2.resize(frame_anterior, (640, 360))
        g1 = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
        g2 = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
        diff = cv2.absdiff(g1, g2)
        pct = cv2.countNonZero(diff) / diff.size
        mov = {"hay": pct > umbral, "intensidad": round(pct * 100, 1), "direccion": "ninguna"}
        if pct > umbral:
            h, w = diff.shape
            izq, der = np.sum(diff[:, :w//2]), np.sum(diff[:, w//2:])
            arr, aba = np.sum(diff[:h//2, :]), np.sum(diff[h//2:, :])
            if der > izq * 1.3: mov["direccion"] = "derecha"
            elif izq > der * 1.3: mov["direccion"] = "izquierda"
            elif aba > arr * 1.3: mov["direccion"] = "abajo"
            elif arr > aba * 1.3: mov["direccion"] = "arriba"
        return mov
    except Exception:
        return {"hay": False, "intensidad": 0, "direccion": "ninguna"}





def sistema_reglas(texto, objetos, movimiento, color_dom, colores_hsv, templates, bg_mask):
    import random

    if texto:
        tl = texto.lower()
        if re.search(r"muerte|morir|game over|perdiste|fallaste", tl):
            return random.choice([
                "Oh no! Animo, esto no termina aqui.",
                "Uy, eso dolio. Pero vamos, a levantarse.",
                "No pasa nada, de los errores se aprende.",
            ])
        if re.search(r"victoria|ganaste|completado|logro|trophy", tl):
            return random.choice([
                "Eso es! Bien jugado.",
                "Lo sabia, sabia que podias.",
                "Que bien se siente ganar, eh?",
            ])
        if re.search(r"peligro|enemigo|boss|jefe|cuidado", tl):
            return random.choice([
                "Cuidado! Algo se acerca...",
                "Ojo ahi, que viene curvas.",
                "Preparate, que esto se pone feo.",
            ])
        if re.search(r"pausa|menu|opciones|configuracion", tl):
            return random.choice([
                "Menu en pausa. Tomate el tiempo que necesites.",
                "Pausa para respirar y planear el proximo paso.",
                "Ajustes abiertos, elige con calma.",
            ])
        if re.search(r"cargando|loading", tl):
            return random.choice([
                "Cargando... ya casi, paciencia.",
                "Mientras carga, cuentame algo.",
                "Cargando, cargando... lista en un momento.",
            ])

    if texto:
        return texto

    if bg_mask and colores_hsv:
        if colores_hsv.get("rojo", 0) > 5000 and bg_mask["porcentaje"] > 5:
            return random.choice(["Accion! Algo se esta moviendo.", "Se esta armando, no te despistes.", "Esto se esta poniendo intenso."])

    info = []

    if colores_hsv and not info:
        if colores_hsv.get("rojo", 0) > 3000:
            info.append(random.choice(["Hay mucho rojo, pelea a la vista?", "Rojo intenso, algo se esta cociendo."]))
        elif colores_hsv.get("verde", 0) > 3000:
            info.append(random.choice(["Verde por todas partes, zona tranquila.", "La calma antes de la tormenta, quizas."]))

    if texto and not info:
        info.append(texto)

    if not info:
        colores_map = {
            "rojo": ["Rojo, senal de peligro.", "Hay bastante rojo por ahi."],
            "naranja": ["Tono anaranjado, algo se calienta?", "Naranja en pantalla."],
            "verde": ["Todo en calma, se puede bajar la guardia.", "Verde, zona segura."],
            "azul": ["Ambiente tranquilo, todo en orden.", "Tonalidad azul, relax."],
            "oscuro": ["Esta oscuro, pero seguimos.", "Oscuridad, a ver que sale."],
            "claro": ["Mucha luz, se ve todo bien.", "Dia despejado en la pantalla."],
        }
        msg = colores_map.get(color_dom)
        if msg:
            return random.choice(msg) if isinstance(msg, list) else msg

    if info:
        return random.choice(info)
    return None


def detectar_colores_hsv(img_np, rangos=None):
    if rangos is None:
        rangos = [
            ("rojo",     (0, 100, 100),   (10, 255, 255)),
            ("rojo2",    (170, 100, 100), (180, 255, 255)),
            ("naranja",  (10, 150, 150),  (25, 255, 255)),
            ("verde",    (40, 80, 80),    (70, 255, 255)),
            ("azul",     (100, 100, 100), (130, 255, 255)),
            ("amarillo", (25, 150, 150),  (35, 255, 255)),
            ("morado",   (130, 80, 80),   (170, 255, 255)),
        ]
    try:
        hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV)
        resultado = {}
        for nombre, bajo, alto in rangos:
            mask = cv2.inRange(hsv, np.array(bajo), np.array(alto))
            pixeles = cv2.countNonZero(mask)
            if pixeles > 1000:
                resultado[nombre.replace("rojo2", "rojo")] = pixeles
        return resultado
    except:
        return {}


_bg_subs = None
_bg_subs_activo = False


def background_subtractor_iniciar():
    global _bg_subs, _bg_subs_activo
    try:
        _bg_subs = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=50, detectShadows=False)
        _bg_subs_activo = True
    except:
        _bg_subs_activo = False


def background_subtractor_aplicar(frame_gray):
    global _bg_subs, _bg_subs_activo
    if not _bg_subs_activo or _bg_subs is None:
        return None
    try:
        fg = _bg_subs.apply(frame_gray)
        _, thresh = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        kernel = np.ones((3, 3), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        pct = cv2.countNonZero(cleaned) / cleaned.size
        return {"mask": cleaned, "porcentaje": round(pct * 100, 1), "hay_movimiento": pct > 0.01}
    except:
        return None



