# ai_scoring.py
def compute_suspicion(face_count, blinking, mouth_open, gaze_off=False, objects_detected=0):
    score = 0.0
    if face_count == 0:
        score += 40
    if face_count > 1:
        score += 30
    if blinking:
        score += 10
    if mouth_open:
        score += 8
    if gaze_off:
        score += 6
    score += min(objects_detected * 6, 20)
    if score > 100:
        score = 100
    return int(score)
