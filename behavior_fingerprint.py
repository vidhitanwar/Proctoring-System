# behavior_fingerprint.py
import numpy as np, json
from pathlib import Path
import matplotlib.pyplot as plt

STORAGE = Path('logs')
STORAGE.mkdir(exist_ok=True)

def compute_baseline_if_needed(username, events, baseline_seconds=20):
    base_file = STORAGE / f"{username}_baseline.json"
    if base_file.exists():
        with open(base_file,'r') as f:
            return json.load(f)
    if not events:
        return None
    start_ts = events[0].get('ts',0)
    window = [e for e in events if e.get('ts',0) - start_ts <= baseline_seconds]
    if not window:
        return None
    bl = {}
    bl['avg_blink'] = float(np.mean([1 if e.get('blink') else 0 for e in window]))
    bl['avg_mouth'] = float(np.mean([1 if e.get('mouth') else 0 for e in window]))
    gazes = [e.get('gaze') for e in window if e.get('gaze')]
    if gazes:
        xs = [g.get('x',0) for g in gazes]
        ys = [g.get('y',0) for g in gazes]
        bl['gaze_mean'] = [float(np.mean(xs)), float(np.mean(ys))]
    else:
        bl['gaze_mean'] = [0.5, 0.5]
    with open(base_file,'w') as f:
        json.dump(bl,f)
    return bl

def process_session_events(username, sid, events):
    heatmap_path = STORAGE / "images"
    heatmap_path.mkdir(parents=True, exist_ok=True)
    xs = [e.get('gaze',{}).get('x') for e in events if e.get('gaze')]
    ys = [e.get('gaze',{}).get('y') for e in events if e.get('gaze')]
    if xs and ys:
        plt.figure(figsize=(6,4))
        plt.hexbin(xs, ys, gridsize=60, cmap='inferno')
        plt.gca().invert_yaxis()
        plt.axis('off')
        img_file = heatmap_path / f"{username}_{sid}_heatmap.png"
        plt.savefig(img_file, bbox_inches='tight', pad_inches=0)
        plt.close()
        return str(img_file)
    return None

def analyze_deviation(username, sid, events, baseline):
    if not events:
        return {}
    bl = baseline or {}
    avg_blink = float(np.mean([1 if e.get('blink') else 0 for e in events]))
    avg_mouth = float(np.mean([1 if e.get('mouth') else 0 for e in events]))
    face_missing = sum(1 for e in events if e.get('face_count',1)==0)
    multiple_faces = sum(1 for e in events if e.get('face_count',1)>1)
    gaze_off = sum(1 for e in events if e.get('gaze_off'))
    deviation = {
        'avg_blink': avg_blink,
        'avg_mouth': avg_mouth,
        'face_missing_count': face_missing,
        'multiple_faces_count': multiple_faces,
        'gaze_off_count': gaze_off,
    }
    total_score = 0
    for e in events[-300:]:
        total_score += compute_suspicion(e.get('face_count',1), e.get('blink',False), e.get('mouth',False), e.get('gaze_off',False), e.get('objects',0))
    avg_score = int(total_score / max(1, min(len(events),300)))
    deviation['avg_suspicion_score'] = avg_score
    heatmap = process_session_events(username, sid, events)
    deviation['heatmap'] = heatmap
    return deviation
