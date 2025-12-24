# proctoring_state.py
class ProctoringState:
    def __init__(self):
        self.last_face_count = 1
        self.last_blink = False
        self.last_mouth = False
        self.last_gaze_off = False
        self.last_objects = 0
        self.suspicion_history = []

    def update(self, face_count, blink, mouth, gaze_off, objects, suspicion):
        self.last_face_count = face_count
        self.last_blink = blink
        self.last_mouth = mouth
        self.last_gaze_off = gaze_off
        self.last_objects = objects
        self.suspicion_history.append(suspicion)
        if len(self.suspicion_history) > 300:
            self.suspicion_history.pop(0)

    def avg_suspicion(self):
        if not self.suspicion_history:
            return 0
        return sum(self.suspicion_history) / len(self.suspicion_history)
