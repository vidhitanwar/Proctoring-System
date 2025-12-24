# ai_reasoner.py
def generate_reasons(analysis):
    reasons = []
    if not analysis:
        return ['No events recorded.']
    if analysis.get('face_missing_count',0) > 5:
        reasons.append('Face missing several times during the test (possible absent or camera issue).')
    if analysis.get('multiple_faces_count',0) > 0:
        reasons.append('Multiple faces detected in the camera at some times (possible unauthorized person present).')
    if analysis.get('avg_mouth',0) > 0.25:
        reasons.append('Significant mouth movement detected (talking or external assistance).')
    if analysis.get('avg_blink',0) > 0.6:
        reasons.append('Unusually high blink activity detected (possible stress or distraction).')
    if analysis.get('avg_suspicion_score',0) > 30:
        reasons.append(f"Overall suspicion score averaged {analysis.get('avg_suspicion_score')}%, review recommended.")
    if analysis.get('heatmap'):
        reasons.append('Attention heatmap generated showing areas of focus during the session.')
    if not reasons:
        reasons.append('No suspicious activity detected.')
    return reasons
