// static/js/test.js
console.log('ExamPro test.js loaded');

let video, startBtn, stopBtn, finishBtn, timerEl;
let stream, captureInterval, t=0, timerInterval;
const frameIntervalMs = 1000;

document.addEventListener('DOMContentLoaded', ()=>{
  video = document.getElementById('video');
  startBtn = document.getElementById('startBtn');
  stopBtn = document.getElementById('stopBtn');
  finishBtn = document.getElementById('finishBtn');
  timerEl = document.getElementById('timer');

  startBtn.onclick = async ()=>{
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width:720, height:540 }, audio: false });
      video.srcObject = stream;
      startCapture();
      startTimer();
    } catch(e){ alert('Camera error: ' + e.message); }
  };

  stopBtn.onclick = ()=>{ stopCapture(); stopTimer(); if(stream) stream.getTracks().forEach(t=>t.stop()); };

  finishBtn.onclick = async ()=>{
    stopCapture(); stopTimer();
    const res = await fetch('/end_test', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: sessionId})});
    const j = await res.json();
    if(j.status === 'ok') {
      window.location = '/analysis/' + encodeURIComponent('{{ current_user.username }}') + '/' + sessionId;
    } else {
      alert('Error finishing test: ' + (j.msg || 'unknown'));
    }
  };
});

function startTimer(){
  if(timerInterval) return;
  t = 0;
  timerInterval = setInterval(()=>{ t++; timerEl.innerText = (String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0')); }, 1000);
}
function stopTimer(){ clearInterval(timerInterval); timerInterval = null; }

function startCapture(){
  if(captureInterval) return;
  const canvas = document.createElement('canvas');
  canvas.width = 640; canvas.height = 480;
  const ctx = canvas.getContext('2d');
  captureInterval = setInterval(async ()=>{
    if (!video || video.readyState < 2) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL('image/jpeg', 0.6);
    try {
      const res = await fetch('/process_frame', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({image: data, session_id: sessionId})});
      const j = await res.json();
      updateUIFromDetection(j);
    } catch(e){
      console.error('frame send error', e);
    }
  }, frameIntervalMs);
}

function stopCapture(){ clearInterval(captureInterval); captureInterval = null; }

function updateUIFromDetection(d){
  if(!d) return;
  document.getElementById('faceDetected').innerText = d.face_count;
  document.getElementById('blink').innerText = d.blink ? 'Yes':'No';
  document.getElementById('mouth').innerText = d.mouth ? 'Yes':'No';
  document.getElementById('gaze').innerText = d.gaze ? (d.gaze.x.toFixed(2)+','+d.gaze.y.toFixed(2)) : '—';
  document.getElementById('suspicion').innerText = d.score + '%';

  // alert area: show banner when suspicion high
  if (d.score >= 50) {
    let a = document.createElement('div'); a.className='alert alert-danger mt-2'; a.innerText = '⚠ High suspicion detected: '+ d.score +'%';
    document.getElementById('alertArea').prepend(a);
    setTimeout(()=>{ try{ a.remove(); }catch(e){} }, 8000);
  }
}
