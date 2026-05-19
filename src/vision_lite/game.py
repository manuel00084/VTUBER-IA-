import re
import numpy as np
import cv2
from collections import Counter
from .ocr import GameOCREngine
from .template import SceneAnalyzer


class NumberReader:
    def __init__(self, ocr_engine=None):
        self._ocr = ocr_engine or GameOCREngine()

    def read(self, frame, region=None, preprocess=True):
        if region:
            x, y, w, h = region
            roi = frame[y:y + h, x:x + w]
        else:
            roi = frame
        results = self._ocr.read(roi, preprocess=preprocess)
        numbers = []
        for r in results:
            nums = re.findall(r'-?\d+(?:[.,]\d+)?', r["text"])
            for n in nums:
                numbers.append({"value": self._parse(n), "text": n,
                                "confidence": r["confidence"]})
        return numbers

    def sum(self, frame, region=None):
        return sum(n["value"] for n in self.read(frame, region))

    @staticmethod
    def _parse(s):
        s = s.replace(",", ".")
        try:
            return int(float(s)) if "." not in s else float(s)
        except ValueError:
            return 0


class ItemIconClassifier:
    def __init__(self, threshold=0.7):
        self._templates = {}
        self._threshold = threshold

    def load(self, name, path):
        tpl = cv2.imread(path, cv2.IMREAD_COLOR)
        if tpl is not None:
            self._templates[name] = tpl

    def detect(self, frame, threshold=None):
        if threshold is None:
            threshold = self._threshold
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]
        results = []
        for name, tpl in self._templates.items():
            tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
            th, tw = tpl_gray.shape
            if th > h or tw > w:
                continue
            res = cv2.matchTemplate(gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= threshold)
            for pt in zip(*loc[::-1]):
                results.append({"class_name": name, "confidence": float(res[pt[1], pt[0]]),
                                "box": [int(pt[0]), int(pt[1]), tw, th]})
        return results


class GameStateMachine:
    def __init__(self):
        self._scene = SceneAnalyzer()
        self._state = "desconocido"
        self._history = []

    def update(self, frame):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        brightness = cv2.mean(hsv)[2] / 255.0

        small_gray = cv2.resize(gray, (64, 48))
        edges = cv2.Canny(small_gray, 30, 100)
        edge_density = np.count_nonzero(edges) / edges.size

        dark_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 80, 80]))
        dark_pct = np.count_nonzero(dark_mask) / (w * h)

        red_mask = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
        red2 = cv2.inRange(hsv, np.array([170, 100, 100]), np.array([180, 255, 255]))
        red_pct = (np.count_nonzero(red_mask) + np.count_nonzero(red2)) / (w * h)

        white_mask = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 30, 255]))
        white_pct = np.count_nonzero(white_mask) / (w * h)

        labels = self._scene.analyze(frame)

        if dark_pct > 0.6 and edge_density < 0.05:
            new_state = "cargando"
        elif dark_pct > 0.4 and brightness < 0.25:
            new_state = "menu"
        elif red_pct > 0.3 and white_pct > 0.02:
            new_state = "muerte"
        elif white_pct > 0.05 and brightness > 0.7:
            new_state = "victoria"
        elif edge_density > 0.06:
            new_state = "partida"
        else:
            new_state = "desconocido"

        self._history.append(new_state)
        if len(self._history) > 5:
            self._history.pop(0)

        self._state = Counter(self._history).most_common(1)[0][0]
        return self._state

    @property
    def state(self):
        return self._state

    def reset(self):
        self._state = "desconocido"
        self._history = []
