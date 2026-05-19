

import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'

try:
    from rapidocr_onnxruntime import RapidOCR
    RAPID_OK = True
except ImportError:
    RAPID_OK = False

import numpy as np
import cv2


class GameOCREngine:
    def __init__(self, lang="es", conf_min=0.3):
        self._conf_min = conf_min
        self._rapid = None

    def _init_rapid(self):
        if RAPID_OK and self._rapid is None:
            try:
                self._rapid = RapidOCR(box_thresh=0.25, text_thresh=0.4, unclip_ratio=2.2)
                return True
            except Exception:
                return False
        return RAPID_OK and self._rapid is not None

    @staticmethod
    def _preprocess(image):
        h, w = image.shape[:2]

        up = cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (0, 0), 15)
        gray = cv2.divide(gray, blur, scale=255)

        lab = cv2.cvtColor(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l = clahe.apply(l)
        contrast = cv2.merge([l, a, b])
        contrast = cv2.cvtColor(contrast, cv2.COLOR_LAB2BGR)

        blurred = cv2.GaussianBlur(contrast, (0, 0), 1.5)
        sharpened = cv2.addWeighted(contrast, 1.5, blurred, -0.5, 0)

        gray2 = cv2.cvtColor(sharpened, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(gray2, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 13, 3)

        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    def read(self, image, conf_min=None, preprocess=True):
        if conf_min is None:
            conf_min = self._conf_min

        if isinstance(image, np.ndarray):
            if len(image.shape) == 3 and image.shape[2] == 4:
                image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
            arr = image
        else:
            arr = np.array(image.convert("RGB"))
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        if preprocess:
            arr = self._preprocess(arr)

        results = []

        if self._init_rapid():
            try:
                rapid_result, elapse = self._rapid(arr)
                if rapid_result:
                    for box, text, conf in rapid_result:
                        if conf is not None and conf >= conf_min and len(text.strip()) > 1:
                            results.append({"text": text, "confidence": float(conf)})
            except Exception:
                pass

        return results

    def read_text(self, image, conf_min=None, preprocess=True):
        results = self.read(image, conf_min, preprocess=preprocess)
        texts = [r["text"] for r in results if len(r["text"].strip()) > 2]
        return " ".join(texts)


