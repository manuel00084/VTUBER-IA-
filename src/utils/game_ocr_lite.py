"""
game_ocr_lite.py - GameOCR Engine v1.3
OCR con RapidOCR optimizado para videojuegos
Precisi�n mejorada con engrosado de texto en baja resoluci�n
"""
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'

import cv2
import numpy as np
import threading
import time
import hashlib

_engine = None
_engine_ready = threading.Event()


def _init_engine():
    global _engine
    try:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR(box_thresh=0.25, text_thresh=0.4, unclip_ratio=2.2)
        print("RapidOCR listo")
    except Exception as e:
        print(f"RapidOCR no disponible: {e}")
        _engine = None
    finally:
        _engine_ready.set()


threading.Thread(target=_init_engine, daemon=True).start()


def _wait_engine(timeout=30.0):
    _engine_ready.wait(timeout)
    return _engine is not None


class GameOCR:
    def __init__(self, max_resolucion=720, cache_duracion=5.0,
                 umbral_cambio=0.04, conf_min=0.3):
        self.max_resolucion = max_resolucion
        self.cache_duracion = cache_duracion
        self.umbral_cambio = umbral_cambio
        self.conf_min = conf_min
        self._ultimo_hash = None
        self._ultimo_resultado = None
        self._ultimo_tiempo = 0
        self._ultimo_frame = None
        self._lock = threading.Lock()

    def _preprocess(self, img):
        try:
            h, w = img.shape[:2]
            if h < 20 or w < 20:
                return img

            up = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

            gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)

            blur = cv2.GaussianBlur(gray, (0, 0), 15)
            norm = cv2.divide(gray, blur, scale=255)

            lab = cv2.cvtColor(cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            contrast = cv2.merge([l, a, b])
            contrast = cv2.cvtColor(contrast, cv2.COLOR_LAB2BGR)

            gray2 = cv2.cvtColor(contrast, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray2, (0, 0), 1.0)
            sharpened = cv2.addWeighted(gray2, 1.8, blurred, -0.8, 0)

            return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
        except Exception:
            return img

    def _reducir(self, img):
        h, w = img.shape[:2]
        lado = max(h, w)
        if lado <= self.max_resolucion:
            return img
        e = self.max_resolucion / lado
        return cv2.resize(img, (int(w * e), int(h * e)), cv2.INTER_LINEAR)

    def _hash(self, img):
        p = cv2.resize(img, (32, 24), cv2.INTER_NEAREST)
        return hashlib.md5(p.tobytes()).hexdigest()

    def _cambio(self, img):
        if self._ultimo_frame is None:
            return True
        d = cv2.absdiff(cv2.resize(self._ultimo_frame, (80, 60)),
                        cv2.resize(img, (80, 60)))
        return np.mean(d) / 255.0 > self.umbral_cambio

    def _ocr_en(self, img):
        """Ejecuta RapidOCR en una imagen."""
        if not _wait_engine():
            return []
        result, _ = _engine(img)
        if result is None:
            return []
        h_img = img.shape[0]
        salida = []
        for box, txt, conf in result:
            txt = txt.strip()
            if len(txt) < 2 or conf < self.conf_min:
                continue
            bx = [int(min(p[0] for p in box)), int(min(p[1] for p in box)),
                  int(max(p[0] for p in box)) - int(min(p[0] for p in box)),
                  int(max(p[1] for p in box)) - int(min(p[1] for p in box))]
            # Filtrar texto demasiado pequeño (menos de 4% de la altura de imagen)
            if bx[3] < h_img * 0.04:
                continue
            salida.append({
                'text': txt,
                'score': float(conf),
                'box': bx
            })
        return salida

    def _deduplicar(self, resultados):
        """Elimina textos casi duplicados, conserva el de mayor confianza."""
        if len(resultados) < 2:
            return resultados
        # Comparar cada par de textos por similitud de caracteres
        ordenados = sorted(resultados, key=lambda r: r['score'], reverse=True)
        unicos = []
        for r in ordenados:
            es_dup = False
            for u in unicos:
                a, b = r['text'].lower(), u['text'].lower()
                min_l = min(len(a), len(b))
                max_l = max(len(a), len(b))
                if max_l < 3:
                    continue
                comunes = sum(1 for i, ca in enumerate(a) if i < len(b) and ca == b[i])
                # Si comparten 70%+ chars exactos en mismas posiciones y tama�o similar
                if comunes / max_l > 0.7 and abs(len(a) - len(b)) < 5:
                    es_dup = True
                    break
            if not es_dup:
                unicos.append(r)
        return unicos

    def read_text(self, img):
        if img is None or img.size == 0:
            return []

        ahora = time.time()
        img_opt = self._preprocess(self._reducir(img))
        h_act = self._hash(img_opt)

        with self._lock:
            if self._ultimo_resultado is not None:
                if (h_act == self._ultimo_hash and
                    ahora - self._ultimo_tiempo < self.cache_duracion):
                    return self._ultimo_resultado
                if (not self._cambio(img_opt) and
                    ahora - self._ultimo_tiempo < self.cache_duracion * 2):
                    return self._ultimo_resultado

        resultados = self._ocr_en(img_opt)

        if len(resultados) < 2:
            try:
                img_full = self._preprocess(img)
                if img_full.shape[0] > img_opt.shape[0] * 1.3:
                    res_full = self._ocr_en(img_full)
                    if len(res_full) > len(resultados):
                        resultados = res_full
            except Exception:
                pass

        # Deduplicar: si hay textos muy parecidos, quedarse solo con el de mayor confianza
        resultados = self._deduplicar(resultados)

        with self._lock:
            self._ultimo_hash = h_act
            self._ultimo_resultado = resultados
            self._ultimo_tiempo = ahora
            self._ultimo_frame = img_opt.copy()

        return resultados


_inst = None
_lock = threading.Lock()


def get_game_ocr(max_resolucion=720, cache_duracion=5.0,
                 umbral_cambio=0.04, conf_min=0.3):
    global _inst
    with _lock:
        if _inst is None:
            _inst = GameOCR(max_resolucion, cache_duracion,
                            umbral_cambio, conf_min)
        return _inst


def ocr_read_text(img, lang=None, max_resolucion=720, cache_duracion=5.0,
                  umbral_cambio=0.04, conf_min=0.3):
    return get_game_ocr(max_resolucion, cache_duracion,
                        umbral_cambio, conf_min).read_text(img)


if __name__ == "__main__":
    import sys, time
    p = sys.argv[1] if len(sys.argv) > 1 else None
    img = cv2.imread(p) if p else np.ones((200, 400, 3), dtype=np.uint8) * 200
    if p and img is None:
        print(f"No se pudo leer: {p}"); sys.exit(1)
    if not p:
        cv2.putText(img, "Hola Mundo", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0), 2)
    t0 = time.time()
    res = ocr_read_text(img, conf_min=0.1)
    print(f"{time.time()-t0:.3f}s | {len(res)} textos")
    for r in res:
        print(f"  '{r['text']}' ({r['score']:.2f})")