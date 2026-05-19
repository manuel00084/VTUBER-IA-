import cv2
import numpy as np


class TemplateDetector:
    def __init__(self):
        self._templates = {}

    def load(self, name, path):
        template = cv2.imread(path, 0)
        if template is not None:
            self._templates[name] = template

    def detect(self, frame_gray, threshold=0.8):
        results = []
        for name, template in self._templates.items():
            result = cv2.matchTemplate(frame_gray, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > threshold:
                h, w = template.shape
                results.append({"name": name, "confidence": float(max_val),
                                "position": max_loc, "size": (w, h)})
        return results


class ColorDetector:
    RANGES = [
        ("rojo", np.array([0, 50, 50]), np.array([10, 255, 255])),
        ("rojo2", np.array([170, 50, 50]), np.array([180, 255, 255])),
        ("azul", np.array([100, 50, 50]), np.array([130, 255, 255])),
        ("verde", np.array([40, 50, 50]), np.array([80, 255, 255])),
        ("amarillo", np.array([20, 50, 50]), np.array([35, 255, 255])),
        ("naranja", np.array([10, 50, 50]), np.array([20, 255, 255])),
        ("morado", np.array([130, 50, 50]), np.array([160, 255, 255])),
        ("rosa", np.array([150, 50, 50]), np.array([170, 255, 255])),
        ("cian", np.array([85, 50, 50]), np.array([100, 255, 255])),
        ("blanco", np.array([0, 0, 200]), np.array([180, 30, 255])),
        ("negro", np.array([0, 0, 0]), np.array([180, 255, 50])),
    ]

    def __init__(self, min_area=150):
        self._min_area = min_area

    def detect(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w = frame.shape[:2]
        total_max = h * w * 0.3
        results = []

        for name, lower, upper in self.RANGES:
            mask = cv2.inRange(hsv, lower, upper)
            mask = cv2.erode(mask, None, iterations=1)
            mask = cv2.dilate(mask, None, iterations=2)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < self._min_area or area > total_max:
                    continue
                x, y, bw, bh = cv2.boundingRect(cnt)
                results.append({"class_name": f"objeto_{name}", "confidence": 0.5,
                                "box": [x, y, bw, bh]})
        return results


class PatternDetector:
    def __init__(self):
        self._orb = cv2.ORB_create(nfeatures=60, scoreType=cv2.ORB_FAST_SCORE)

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        tiny = cv2.resize(gray, (64, 48))
        h, w = frame.shape[:2]
        results = []

        kp, des = self._orb.detectAndCompute(tiny, None)
        if des is not None and len(kp) >= 4:
            groups, used = [], set()
            for i in range(len(kp)):
                if i in used:
                    continue
                group = [i]
                used.add(i)
                for j in range(i + 1, len(kp)):
                    if j in used:
                        continue
                    if cv2.norm(des[i], des[j], cv2.NORM_HAMMING) < 20:
                        group.append(j)
                        used.add(j)
                if len(group) > 1:
                    groups.append(group)

            scale_x, scale_y = w / 128, h / 96
            for g in groups[:2]:
                xs = [int(kp[i].pt[0] * scale_x) for i in g]
                ys = [int(kp[i].pt[1] * scale_y) for i in g]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)
                results.append({"class_name": "patron_repetido", "confidence": 0.6,
                                "box": [x_min, y_min, x_max - x_min + 10, y_max - y_min + 10]})

        return results


class SceneAnalyzer:
    RANGES = [
        ("verde", np.array([35, 40, 40]), np.array([85, 255, 255])),
        ("azul", np.array([100, 40, 40]), np.array([130, 255, 255])),
        ("marron", np.array([10, 40, 40]), np.array([25, 255, 200])),
        ("gris", np.array([0, 0, 80]), np.array([180, 30, 180])),
        ("rojo_fuego", np.array([0, 100, 100]), np.array([15, 255, 255])),
        ("negro_oscuro", np.array([0, 0, 0]), np.array([180, 255, 60])),
        ("blanco_nieve", np.array([0, 0, 200]), np.array([180, 50, 255])),
        ("cian_espacio", np.array([90, 50, 50]), np.array([110, 255, 255])),
        ("naranja_ciudad", np.array([5, 50, 50]), np.array([15, 255, 200])),
        ("morado_cyber", np.array([125, 50, 50]), np.array([145, 255, 255])),
    ]

    def analyze(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w = frame.shape[:2]
        total = h * w

        brightness = cv2.mean(hsv)[2] / 255.0

        small = cv2.resize(gray, (64, 48))
        edges = cv2.Canny(small, 30, 100)
        edge_density = np.count_nonzero(edges) / edges.size

        coarse = cv2.Canny(cv2.resize(gray, (64, 48)), 100, 200)
        coarse_density = np.count_nonzero(coarse) / coarse.size

        texture = float(cv2.Laplacian(small, cv2.CV_64F).var())

        pcts = {}
        for name, lo, hi in self.RANGES:
            mask = cv2.inRange(hsv, lo, hi)
            pct = cv2.countNonZero(mask) / total
            if pct > 0.10:
                pcts[name] = round(pct * 100)

        labels = []
        if brightness < 0.2:
            labels.append("escenario_oscuro")
        elif brightness > 0.7:
            labels.append("escenario_luminoso")

        g = pcts.get
        if g("cian_espacio", 0) > 25 and coarse_density < 0.04:
            labels.append("escenario_espacio")
        elif g("verde", 0) > 25:
            labels.append("escenario_bosque" if edge_density > 0.1 else "escenario_llanura")
        elif g("azul", 0) > 25:
            labels.append("escenario_rio" if coarse_density > 0.06 else "escenario_mar")
        elif g("morado_cyber", 0) > 15 or (g("negro_oscuro", 0) > 25 and texture > 200):
            labels.append("escenario_cyberpunk")
        elif g("gris", 0) > 35 and coarse_density > 0.08:
            labels.append("escenario_interior")
        elif g("naranja_ciudad", 0) > 15 or (g("gris", 0) > 20 and coarse_density > 0.06):
            labels.append("escenario_ciudad")
        elif g("rojo_fuego", 0) > 15:
            labels.append("escenario_infierno")
        elif g("marron", 0) > 25:
            labels.append("escenario_desierto")
        elif g("blanco_nieve", 0) > 25:
            labels.append("escenario_nieve")
        elif g("negro_oscuro", 0) > 35:
            labels.append("escenario_mazmorra")
        else:
            labels.append("escenario_exterior")

        return labels


class ShapeDetector:
    def __init__(self, min_area=200):
        self._min_area = min_area

    def detect(self, frame):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        half = cv2.resize(gray, (w // 2, h // 2))
        hh, hw = half.shape
        results = []

        edges = cv2.Canny(half, 40, 120)
        edges = cv2.dilate(edges, None, iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._min_area // 4 or area > hw * hh * 0.3:
                continue

            perim = cv2.arcLength(cnt, True)
            if perim == 0:
                continue

            circularity = 4 * np.pi * area / (perim * perim)
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            convexity = area / hull_area if hull_area > 0 else 1

            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / max(bh, 1)
            approx = cv2.approxPolyDP(cnt, 0.04 * perim, True)
            vertices = len(approx)

            if circularity > 0.85 and convexity > 0.9:
                label = "circular"
                conf = min(0.7, circularity)
            elif convexity < 0.7:
                label = "irregular"
                conf = 0.4
            elif vertices == 3:
                label = "triangular"
                conf = 0.6
            elif vertices == 4:
                if 0.9 < aspect < 1.1:
                    label = "cuadrado"
                    conf = 0.65
                else:
                    label = "rectangular"
                    conf = 0.6
            elif vertices >= 6 and circularity < 0.7:
                label = "estrella"
                conf = 0.5
            else:
                label = "poligono"
                conf = 0.45

            if aspect > 4:
                label = "alargado"
                conf = 0.55

            results.append({"class_name": f"forma_{label}", "confidence": conf,
                            "box": [x * 2, y * 2, bw * 2, bh * 2],
                            "shape": {"vertices": vertices, "circularidad": round(circularity, 3),
                                      "aspecto": round(aspect, 2), "convexidad": round(convexity, 3)}})

        return results
