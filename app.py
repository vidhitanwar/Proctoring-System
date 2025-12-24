# app.py (REPLACE your current file with this)
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import mysql.connector, os, json, datetime
from pathlib import Path
from ai_scoring import compute_suspicion
from behavior_fingerprint import compute_baseline_if_needed, analyze_deviation
from ai_reasoner import generate_reasons
from proctoring_state import ProctoringState
import base64
from io import BytesIO
from PIL import Image
import cv2
import numpy as np
from facial_detections import get_face_landmarks, detect_faces

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'replace_with_strong_key')

DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '',
    'database': 'quizo'
}

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id_, username):
        self.id = id_
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute('SELECT id, username FROM users WHERE id=%s', (user_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return User(row[0], row[1])
    except Exception as e:
        print('DB load_user error:', e)
    return None

LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)
(IMAGES_DIR := LOG_DIR / "images").mkdir(exist_ok=True)
STATE = {}   # in-memory ProctoringState per (username, session_id)
FLAGS_FILE = LOG_DIR / "flags.json"
if not FLAGS_FILE.exists():
    FLAGS_FILE.write_text(json.dumps({}))  # structure: {username: [{session_id, ts, score, reason}]}

# ---------- helpers ----------
def add_flag(username, session_id, score, reason):
    data = json.loads(FLAGS_FILE.read_text())
    data.setdefault(username, [])
    data[username].append({'session_id': session_id, 'ts': datetime.datetime.utcnow().isoformat(), 'score': int(score), 'reason': reason})
    FLAGS_FILE.write_text(json.dumps(data))

def get_user_flags(username):
    data = json.loads(FLAGS_FILE.read_text())
    return data.get(username, [])

def save_session_events(username, session_id, events):
    p = LOG_DIR / f"{username}_{session_id}.json"
    with open(p,'w') as f:
        json.dump(events, f)

def load_session_events(username, session_id):
    p = LOG_DIR / f"{username}_{session_id}.json"
    if not p.exists():
        return []
    with open(p,'r') as f:
        return json.load(f)

# ---------- routes ----------
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute('INSERT INTO users (username, password) VALUES (%s,%s)', (username, password))
            conn.commit()
            conn.close()
            flash('Account created. Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error creating account: ' + str(e))
            return redirect(url_for('signup'))
    return render_template('signup.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute('SELECT id, username FROM users WHERE username=%s AND password=%s', (username,password))
            row = cur.fetchone()
            conn.close()
            if row:
                user = User(row[0], row[1])
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('Invalid credentials')
            return redirect(url_for('login'))
        except Exception as e:
            flash('DB error: ' + str(e))
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user.username
    # list sessions (raw logs) and flags
    sessions = sorted([p.stem for p in LOG_DIR.glob(f"{user}_*.json") if not p.name.endswith("_analysis.json")], reverse=True)
    flags = get_user_flags(user)
    return render_template('dashboard.html', username=user, sessions=sessions, flags=flags)

@app.route('/start_test')
@login_required
def start_test():
    session_id = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
    # create empty events list file
    user = current_user.username
    p = LOG_DIR / f"{user}_{session_id}.json"
    p.write_text(json.dumps([]))
    STATE[(user, session_id)] = ProctoringState()
    return render_template('test.html', session_id=session_id)

@app.route('/process_frame', methods=['POST'])
@login_required
def process_frame():
    data = request.get_json()
    img_b64 = data.get('image')
    session_id = data.get('session_id')
    if not img_b64 or not session_id:
        return jsonify({'error':'missing'}),400

    # decode image
    header, encoded = img_b64.split(',',1) if ',' in img_b64 else (None, img_b64)
    img_bytes = base64.b64decode(encoded)
    img = Image.open(BytesIO(img_bytes)).convert('RGB')
    frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    # run detections
    faces = detect_faces(frame)
    landmarks_list = get_face_landmarks(frame)
    face_count = len(faces)
    blink = False; mouth = False; gaze_off = False; objects = 0; gaze = None

    if landmarks_list:
        lm = landmarks_list[0]
        try:
            from blink_detection import is_blinking
            from mouth_tracking import is_talking
            blink, ear = is_blinking(lm)
            mouth, mouth_r = is_talking(lm)
            h, w = frame.shape[:2]
            # approximate gaze using nose tip (index 1)
            if len(lm) > 1:
                nx, ny = lm[1][0]/w, lm[1][1]/h
                gaze = {'x': float(nx), 'y': float(ny)}
                gaze_off = (nx < 0.18 or nx > 0.82) or (ny < 0.18 or ny > 0.82)
        except Exception as e:
            print("blink/mouth error:", e)

    score = compute_suspicion(face_count, blink, mouth, gaze_off, objects)

    # update state and save event
    user = current_user.username
    evt = {'session_id': session_id, 'ts': datetime.datetime.utcnow().timestamp(),
           'face_count': face_count, 'blink': blink, 'mouth': mouth, 'gaze': gaze, 'gaze_off': gaze_off, 'objects': objects, 'score': score}
    events = load_session_events(user, session_id)
    events.append(evt)
    save_session_events(user, session_id, events)

    # update in-memory state and check flags threshold
    key = (user, session_id)
    state = STATE.get(key)
    if state is None:
        state = ProctoringState(); STATE[key] = state
    state.update(face_count, blink, mouth, gaze_off, objects, score)

    # Raise flag if score crosses threshold or face missing repeatedly
    reason = None
    if score >= 50:
        reason = f'High suspicion score {score}%'
        add_flag(user, session_id, score, reason)
    # repeated face missing
    missing_count = sum(1 for e in events[-30:] if e.get('face_count',1)==0)
    if missing_count >= 5:
        add_flag(user, session_id, 80, 'Face missing repeatedly')

    # return detection summary
    return jsonify({'face_count':face_count, 'blink':blink, 'mouth':mouth, 'gaze':gaze, 'gaze_off':gaze_off, 'objects':objects, 'score':score})

@app.route('/live_monitor/<username>/<session_id>')
@login_required
def live_monitor(username, session_id):
    # open live monitor page (client can poll server or use logs)
    return render_template('live_monitor.html', username=username, session_id=session_id)

@app.route('/my_reports')
@login_required
def my_reports():
    user = current_user.username
    # show all analyzed sessions
    analyses = []
    for p in LOG_DIR.glob(f"{user}_*_analysis.json"):
        with open(p,'r') as f:
            analyses.append({'file':p.name, 'data': json.load(f)})
    return render_template('my_reports.html', analyses=analyses)

@app.route('/end_test', methods=['POST'])
@login_required
def end_test():
    data = request.get_json()
    sid = data.get('session_id')
    user = current_user.username
    events = load_session_events(user, sid)
    baseline = compute_baseline_if_needed(user, events)
    analysis = analyze_deviation(user, sid, events, baseline)
    reasons = generate_reasons(analysis)
    out_path = LOG_DIR / f"{user}_{sid}_analysis.json"
    with open(out_path,'w') as f:
        json.dump({'analysis':analysis,'reasons':reasons}, f)
    return jsonify({'status':'ok','analysis':analysis,'reasons':reasons})

@app.route('/analysis/<username>/<sid>')
@login_required
def view_analysis(username, sid):
    path = LOG_DIR / f"{username}_{sid}_analysis.json"
    if not path.exists():
        return 'No analysis found', 404
    with open(path,'r') as f:
        data = json.load(f)
    return render_template('analysis.html', username=username, sid=sid, analysis=data['analysis'], reasons=data['reasons'])

@app.route('/static/images/<path:filename>')
def serve_image(filename):
    return send_from_directory('static/images', filename)

@app.route('/flags')
@login_required
def flags_page():
    user = current_user.username
    flags = get_user_flags(user)
    return render_template('flags.html', flags=flags)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

# ------------------ Test creation & quiz endpoints ------------------

import uuid
from flask import Markup

TESTS_DIR = LOG_DIR / "tests"
TESTS_DIR.mkdir(exist_ok=True)

@app.route('/create_test', methods=['GET','POST'])
@login_required
def create_test():
    # Simple UI for creating a test (stored as JSON)
    if request.method == 'POST':
        payload = request.get_json()
        # expected payload: { "title": "Sample", "questions": [ {q, options:[..], answer:0}, ... ] }
        tid = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S') + "_" + uuid.uuid4().hex[:6]
        p = TESTS_DIR / f"{tid}.json"
        with open(p,'w') as f:
            json.dump(payload, f)
        return jsonify({'status':'ok','test_id': tid})
    # GET -> render create test UI
    return render_template('create_test.html')

@app.route('/get_test/<test_id>')
@login_required
def get_test(test_id):
    p = TESTS_DIR / f"{test_id}.json"
    if not p.exists():
        return jsonify({'error':'not found'}),404
    with open(p,'r') as f:
        return jsonify(json.load(f))

@app.route('/take_test/<test_id>')
@login_required
def take_test(test_id):
    # Render premium test-taking page (client will fetch questions)
    return render_template('take_test.html', test_id=test_id)

@app.route('/submit_test', methods=['POST'])
@login_required
def submit_test():
    # Evaluate answers, compute score, store result, and optionally run final analysis
    data = request.get_json()
    test_id = data.get('test_id')
    answers = data.get('answers', {})  # dict {q_index: selected_index}
    user = current_user.username
    p = TESTS_DIR / f"{test_id}.json"
    if not p.exists():
        return jsonify({'status':'error','msg':'test missing'}),400
    with open(p,'r') as f:
        test = json.load(f)
    questions = test.get('questions', [])
    total = len(questions)
    correct = 0
    for i, q in enumerate(questions):
        correct_index = int(q.get('answer', 0))
        sel = answers.get(str(i))
        if sel is not None and int(sel) == correct_index:
            correct += 1
    score_pct = int((correct / max(1,total)) * 100)
    # save result file
    resp = { 'user': user, 'test_id': test_id, 'ts': datetime.datetime.utcnow().isoformat(),
             'score': score_pct, 'total_questions': total, 'correct': correct }
    resfile = LOG_DIR / f"{user}_test_{test_id}_result.json"
    with open(resfile,'w') as f:
        json.dump(resp, f)
    # optionally call end_test analysis for proctoring logs (if session exists)
    session_id = data.get('session_id')
    if session_id:
        # try to run analysis same as end_test
        events = load_session_events(user, session_id)
        baseline = compute_baseline_if_needed(user, events)
        analysis = analyze_deviation(user, session_id, events, baseline)
        reasons = generate_reasons(analysis)
        out_path = LOG_DIR / f"{user}_{session_id}_analysis.json"
        with open(out_path,'w') as f:
            json.dump({'analysis':analysis,'reasons':reasons}, f)
    return jsonify({'status':'ok','score': score_pct, 'correct': correct, 'total': total})
