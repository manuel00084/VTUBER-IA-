import cv2
import numpy as np

try:
    import mediapipe as mp
    MP_OK = True
except ImportError:
    MP_OK = False


class PoseDetector:
    def __init__(self, static_mode=False, model_complexity=1, smooth=True,
                 min_detection=0.5, min_tracking=0.5):
        self._pose = None
        if MP_OK:
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=static_mode,
                model_complexity=model_complexity,
                smooth_landmarks=smooth,
                min_detection_confidence=min_detection,
                min_tracking_confidence=min_tracking)
        self._landmarks = None

    def detect(self, frame):
        if self._pose is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        self._landmarks = result.pose_landmarks
        return self._landmarks

    def get_landmarks(self, frame_shape):
        if self._landmarks is None:
            return []
        h, w = frame_shape[:2]
        pts = []
        for lm in self._landmarks.landmark:
            pts.append({"x": int(lm.x * w), "y": int(lm.y * h),
                        "z": lm.z, "visibility": lm.visibility})
        return pts

    def draw(self, frame):
        if self._landmarks is None:
            return frame
        mp.solutions.drawing_utils.draw_landmarks(
            frame, self._landmarks,
            mp.solutions.pose.POSE_CONNECTIONS,
            mp.solutions.drawing_utils.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
            mp.solutions.drawing_utils.DrawingSpec(color=(0, 0, 255), thickness=2))
        return frame

    def close(self):
        if self._pose:
            self._pose.close()
            self._pose = None
