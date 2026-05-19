import cv2
import numpy as np


class VisualCache:
    def __init__(self, hash_size=8, diff_threshold=2000000):
        self._hash_size = hash_size
        self._diff_threshold = diff_threshold
        self._prev_hash = None
        self._prev_gray = None
        self._skip = 0

    def _dhash(self, gray):
        resized = cv2.resize(gray, (self._hash_size + 1, self._hash_size))
        diff = (resized[:, 1:] > resized[:, :-1]).astype(np.uint8)
        bits = diff.flatten()
        h = 0
        for bit in bits:
            h = (h << 1) | int(bit)
        return h

    def check(self, frame):
        if self._skip > 0:
            self._skip -= 1
            return False

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h = self._dhash(gray)

        if self._prev_hash is not None and h == self._prev_hash:
            return False

        if self._prev_gray is not None:
            diff = cv2.absdiff(self._prev_gray, gray)
            score = int(np.sum(diff))
            if score < self._diff_threshold:
                return False

        self._prev_hash = h
        self._prev_gray = gray
        self._skip = 3
        return True

    def reset(self):
        self._prev_hash = None
        self._prev_gray = None
        self._skip = 0
