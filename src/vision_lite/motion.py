import cv2
import numpy as np


class MotionDetector:
    def __init__(self):
        self._gray_prev = None
        self._flow_prev = None
        self._hist_prev = None

    def detect(self, frame, threshold=None):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]

        if self._gray_prev is None:
            self._gray_prev = gray
            return False, 0, []

        diff = cv2.absdiff(self._gray_prev, gray)
        motion_score = int(np.sum(diff))
        self._gray_prev = gray

        if threshold is None:
            mean_diff = int(np.mean(diff))
            threshold = max(150000, mean_diff * h * w // 4)

        detected = motion_score > threshold
        regions = []
        if detected:
            _, thresh = cv2.threshold(diff, max(25, int(np.mean(diff) * 2)), 255, cv2.THRESH_BINARY)
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            min_area = max(300, h * w // 3000)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area or area > h * w * 0.6:
                    continue
                x, y, bw, bh = cv2.boundingRect(cnt)
                regions.append({"box": [x, y, bw, bh], "area": int(area)})

        return detected, motion_score, regions

    def detect_optical_flow(self, frame):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (w // 4, h // 4))
        result = {"magnitude": 0, "direction": None, "scroll": False, "shake": False}

        if self._flow_prev is not None:
            flow = cv2.calcOpticalFlowFarneback(
                self._flow_prev, small, None, 0.5, 3, 9, 3, 5, 1.2, 0
            )
            fx = float(flow[..., 0].mean())
            fy = float(flow[..., 1].mean())
            mag = float(np.sqrt(fx * fx + fy * fy))
            flow_std = float(flow[..., 0].std() + flow[..., 1].std())

            result["magnitude"] = mag
            if mag > 2.0:
                if abs(fx) > abs(fy):
                    result["direction"] = "derecha" if fx > 0 else "izquierda"
                else:
                    result["direction"] = "abajo" if fy > 0 else "arriba"
                if mag > 5.0 and flow_std < mag * 0.4:
                    result["scroll"] = True
                if flow_std > 15:
                    result["shake"] = True

        self._flow_prev = small
        return result

    def detect_transition(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (32, 24))
        hist = cv2.calcHist([small], [0], None, [32], [0, 256])
        cv2.normalize(hist, hist)

        if self._hist_prev is None:
            self._hist_prev = hist
            return False, 0

        diff = cv2.compareHist(self._hist_prev, hist, cv2.HISTCMP_CHISQR)
        self._hist_prev = hist
        return diff > 60, float(diff)

    def reset(self):
        self._gray_prev = None
        self._flow_prev = None
        self._hist_prev = None


