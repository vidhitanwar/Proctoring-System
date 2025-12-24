# mouth_tracking.py
import numpy as np
def mouth_open_ratio(landmarks):
    if not landmarks:
        return 0.0
    top = np.array(landmarks[13][:2])
    bottom = np.array(landmarks[14][:2])
    left = np.array(landmarks[78][:2])
    right = np.array(landmarks[308][:2])
    vertical = np.linalg.norm(top - bottom)
    horizontal = np.linalg.norm(left - right)
    if horizontal < 1e-6:
        return 0.0
    return vertical / horizontal

def is_talking(landmarks, threshold=0.35):
    r = mouth_open_ratio(landmarks)
    return (r > threshold), r
