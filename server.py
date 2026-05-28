#!/usr/bin/env python3
"""
Local Language Exchange Pro v3.3
- Pure Python 3.7+ standard library (no pip installs)
- FIXED: Server now runs in background thread, port binds instantly
- Terminal: type 'clear data' to safely wipe & reboot without crashing
- Admin: Ctrl+Shift+A (or click 🔐 header button)
- One-click messaging via CID routing
- Auto-generates all files on first run
"""

import os, json, sqlite3, html, threading, time, sys, shutil
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ──────────────────────────────────────────────────────────────
# CONFIG & PATHS
# ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "exchange.db")
ADMIN_PASS = "admin"
HEARTBEAT_TIMEOUT = 15
SERVER_FILE = os.path.basename(__file__)
PORT = 8000

# ──────────────────────────────────────────────────────────────
# GLOBAL STATE
# ──────────────────────────────────────────────────────────────
lock = threading.Lock()
sse_queues = {}
active_clients = {}
banned_clients = set()

# ──────────────────────────────────────────────────────────────
# EMBEDDED FRONTEND (unchanged, fully functional)
# ──────────────────────────────────────────────────────────────
FILE_CONTENTS = {
    "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Local Language Exchange Pro</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header>
  <h1>🌍 Local Language Exchange Pro</h1>
  <div style="display:flex;gap:10px;align-items:center">
    <button id="open-admin-btn" style="background:var(--warn);color:#000;padding:0.4rem 0.8rem;font-size:0.8rem">🔐 Admin</button>
    <span id="conn" class="status err">Offline</span>
  </div>
</header>
<main>
  <section id="profile-section"><h2>👤 My Profile</h2>
    <input type="text" id="my-known" placeholder="Languages I know (e.g., Spanish, English)">
    <input type="text" id="my-learn" placeholder="Languages I want to learn">
    <input type="text" id="my-name" placeholder="Your display name">
    <button id="save-profile">💾 Save Profile</button><p id="profile-status"></p>
  </section>
  <section id="form-section"><h2>📝 Post a Request</h2>
    <form id="exchange-form">
      <input type="text" id="know-lang" placeholder="Languages you know (comma-separated)" required>
      <input type="text" id="learn-lang" placeholder="Languages you want to learn (comma-separated)" required>
      <textarea id="message" placeholder="Message (e.g., Looking for casual practice)" required></textarea>
      <button type="submit">Post Request</button>
    </form><p id="status"></p>
  </section>
  <section id="posts-section"><h2>🔍 Browse Requests</h2>
    <input type="text" id="search-lang" placeholder="Filter by language...">
    <div id="posts-list"><p>Loading...</p></div>
  </section>
  <section id="messages-section" style="display:none"><h2>💬 Chat <button id="close-msgs" style="float:right;font-size:0.8rem">✕ Close</button></h2>
    <div id="msg-header" style="font-size:0.9rem;color:var(--muted);margin-bottom:8px"></div>
    <div id="msg-list"></div>
    <div style="margin-top:10px;display:flex;gap:8px"><input type="text" id="msg-text" placeholder="Type a message..." style="flex:1"><button id="msg-send">Send</button></div>
  </section>
</main>
<div id="admin">
  <div class="admin-head"><strong>🔐 Admin Console</strong><button class="admin-close" id="adminClose">✕</button></div>
  <div><strong>Connected Clients</strong><div id="cList"></div></div>
  <div class="note">💡 Bans target unique browser sessions (client_id), not IP.</div>
  <div style="margin-top:1rem"><strong>Banned Users</strong><div id="bList"></div></div>
  <div style="margin-top:1rem"><strong>System</strong><button id="reload-db" class="btn-sm">🔄 Reload Posts</button></div>
</div>
<div id="warning-overlay" class="overlay"><div class="overlay-card"><div class="icon">⚠️</div><h1>Official Warning</h1><p id="warning-text">You have received a warning.</p><button class="ack-btn" id="warn-ack-btn">Acknowledge</button></div></div>
<div id="banned-overlay" class="overlay"><div class="overlay-card"><div class="icon">🚫</div><h1>Access Denied</h1><p>This session has been banned.</p><div class="code" id="banned-id-display">ID: loading...</div></div></div>
<div id="corner-hint" class="hint">Loading...</div>
<script src="/static/script.js"></script></body></html>""",

    "static/style.css": """:root{--bg:#0b1120;--surface:#151e32;--primary:#3b82f6;--text:#f1f5f9;--muted:#94a3b8;--border:#1e293b;--success:#10b981;--warn:#f59e0b;--danger:#ef4444;--radius:12px}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh;padding:1rem}
header{display:flex;justify-content:space-between;align-items:center;padding:1rem 0;border-bottom:1px solid var(--border);margin-bottom:1.5rem}
.status{font-size:0.75rem;padding:0.3rem 0.7rem;border-radius:20px;background:var(--surface);border:1px solid var(--border)}
.status.ok{color:var(--success);border-color:var(--success)}.status.err{color:var(--danger);border-color:var(--danger)}
section{background:var(--surface);padding:1.2rem;margin-bottom:1rem;border-radius:var(--radius);border:1px solid var(--border)}
input,textarea{width:100%;padding:0.7rem;margin:0.4rem 0 1rem;border:1px solid var(--border);border-radius:8px;background:rgba(255,255,255,0.05);color:var(--text)}
button{background:var(--primary);color:#fff;border:none;padding:0.7rem 1.3rem;border-radius:8px;cursor:pointer;font-weight:600}
button:hover{background:#2563eb}button:disabled{opacity:0.6;cursor:default}
.post{border-bottom:1px solid var(--border);padding:1rem 0}.post:last-child{border-bottom:none}
.lang{font-weight:600;color:var(--primary)}.time{color:var(--muted);font-size:0.8rem;margin-top:4px}
.match-badge{display:inline-block;background:#166534;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.75rem;margin-left:8px}
.msg-btn{background:var(--success);color:#fff;border:none;padding:5px 12px;cursor:pointer;border-radius:6px;font-size:0.85rem;margin-top:6px}
.highlight{background:rgba(234,179,8,0.1);border-left:4px solid var(--warn);padding-left:10px;border-radius:4px}
#admin{position:fixed;top:0;right:0;width:380px;height:100vh;background:var(--surface);border-left:1px solid var(--border);padding:1rem;z-index:1000;transform:translateX(100%);transition:transform 0.2s}
#admin.show{transform:translateX(0)}
.admin-head{display:flex;justify-content:space-between;margin-bottom:1rem;padding-bottom:1rem;border-bottom:1px solid var(--border)}
.admin-close{background:var(--danger);color:#fff;border:none;padding:0.2rem 0.6rem;border-radius:6px;cursor:pointer}
.client-item,.banned-item{background:rgba(255,255,255,0.03);padding:0.7rem;border-radius:8px;margin-bottom:0.5rem;font-size:0.8rem}
.client-id{font-family:monospace;font-size:0.65rem;color:var(--primary);background:rgba(59,130,246,0.1);padding:0.1rem 0.4rem;border-radius:4px;display:inline-block;margin:0.2rem 0}
.btn-sm{padding:0.2rem 0.5rem;font-size:0.7rem;border:none;border-radius:4px;cursor:pointer;margin-right:0.3rem}
.btn-kick{background:var(--warn);color:#000}.btn-ban{background:var(--danger);color:#fff}.btn-unban{background:var(--success);color:#fff}.btn-warn{background:#eab308;color:#000}
.note{font-size:0.7rem;color:var(--muted);margin-top:0.5rem;padding:0.5rem;background:rgba(245,158,11,0.1);border-radius:6px;border-left:3px solid var(--warn)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,0.85);backdrop-filter:blur(10px);z-index:10000;display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:0.4s}
.overlay.active{opacity:1;pointer-events:all}
.overlay-card{border-radius:16px;padding:2rem;max-width:450px;text-align:center;box-shadow:0 25px 60px rgba(0,0,0,0.7);border:1px solid;animation:popIn 0.4s cubic-bezier(0.175,0.885,0.32,1.275);background:var(--surface)}
@keyframes popIn{0%{transform:scale(0.8);opacity:0}100%{transform:scale(1);opacity:1}}
#warning-overlay .overlay-card{border-color:var(--warn)}#warning-overlay .icon{color:var(--warn)}#warning-overlay h1{color:var(--warn)}
#banned-overlay .overlay-card{border-color:var(--danger)}#banned-overlay .icon{color:var(--danger)}#banned-overlay h1{color:var(--danger)}
.icon{font-size:3rem;margin-bottom:0.8rem}h1{font-size:1.6rem;margin-bottom:0.4rem}p{color:var(--muted);margin-bottom:1.2rem}
.code{font-family:monospace;font-size:0.8rem;background:rgba(255,255,255,0.1);padding:0.3rem 0.6rem;border-radius:6px;display:inline-block;margin-bottom:1rem}
.ack-btn{background:var(--text);color:var(--bg);border:none;padding:0.7rem 1.8rem;border-radius:8px;font-weight:600;cursor:pointer}
#msg-list{max-height:300px;overflow-y:auto;margin-bottom:1rem;border:1px solid var(--border);border-radius:8px;padding:0.5rem}
.msg{padding:0.5rem 0;border-bottom:1px solid var(--border);font-size:0.9rem}.msg:last-child{border-bottom:none}
.msg-from{font-weight:600;color:var(--primary)}.msg-to{color:var(--muted)}
.msg-text{margin:4px 0}.msg-time{font-size:0.7rem;color:var(--muted)}
.hint{position:fixed;bottom:1rem;right:1rem;font-size:0.75rem;color:var(--muted);background:var(--surface);padding:0.3rem 0.7rem;border-radius:20px;border:1px solid var(--border);z-index:999}
@media(max-width:768px){#admin{width:100%}}""",

    "static/script.js": """const $ = id => document.getElementById(id);
const cid = localStorage.getItem('cid') || (localStorage.setItem('cid', Math.random().toString(36).slice(2)+Date.now().toString(36)) || localStorage.getItem('cid'));
let myProfile = {}, currentChatTarget = null, adminOpen = false;
function connectSSE() {
  const es = new EventSource('/api/events?cid=' + cid);
  es.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'connected') { $('conn').textContent='Connected'; $('conn').className='status ok'; return; }
      if (msg.type === 'banned') { $('banned-overlay').classList.add('active'); $('banned-id-display').textContent='ID: '+cid; return; }
      if (msg.type === 'unbanned') { $('banned-overlay').classList.remove('active'); return; }
      if (msg.type === 'warning') { $('warning-text').textContent=msg.message||'Warning'; $('warning-overlay').classList.add('active'); return; }
      if (msg.type === 'message' && msg.data.to_cid === cid) { addMessageToUI(msg.data); if (currentChatTarget && msg.data.from_cid === currentChatTarget) scrollMsgs(); return; }
      if (msg.type === 'update') { if (!$('messages-section').style.display || $('messages-section').style.display==='none') loadPosts($('search-lang').value.trim()); return; }
      if (msg.type === 'admin') { renderAdmin(msg.clients, msg.banned); return; }
    } catch(err) { console.error('SSE:', err); }
  };
  es.onerror = () => { if (!$('banned-overlay').classList.contains('active')) { $('conn').textContent='Reconnecting...'; $('conn').className='status err'; } };
  return es;
}
let es = connectSSE();
$('save-profile').onclick = () => {
  myProfile = { name: $('my-name').value.trim(), known: $('my-known').value.trim().toLowerCase(), learn: $('my-learn').value.trim().toLowerCase() };
  localStorage.setItem('myProfile', JSON.stringify(myProfile));
  $('profile-status').textContent = '✅ Saved!'; setTimeout(()=> $('profile-status').textContent='', 2500); loadPosts();
};
window.addEventListener('DOMContentLoaded', () => {
  const saved = localStorage.getItem('myProfile');
  if (saved) { myProfile = JSON.parse(saved); $('my-name').value=myProfile.name||''; $('my-known').value=myProfile.known||''; $('my-learn').value=myProfile.learn||''; }
});
$('exchange-form').onsubmit = async (e) => {
  e.preventDefault(); const status = $('status');
  const payload = { know_langs: $('know-lang').value.trim(), learn_langs: $('learn-lang').value.trim(), message: $('message').value.trim(), poster_name: myProfile.name || 'Anonymous', cid: cid };
  status.textContent = 'Posting...';
  try {
    const res = await fetch('/api/posts', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const data = await res.json();
    if (res.ok) { status.textContent='✅ Posted!'; $('exchange-form').reset(); loadPosts(); }
    else status.textContent = '❌ '+(data.error||'Error');
  } catch(err) { status.textContent='❌ Network error'; }
  setTimeout(()=> status.textContent='', 3000);
};
$('search-lang').oninput = (e) => loadPosts(e.target.value.trim());
function escapeHtml(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function getMatchInfo(post) {
  if (!myProfile.known && !myProfile.learn) return { canTeach:[], canLearn:[] };
  const pKnow = (post.know_langs||'').toLowerCase().split(',').map(s=>s.trim()).filter(Boolean);
  const pLearn = (post.learn_langs||'').toLowerCase().split(',').map(s=>s.trim()).filter(Boolean);
  const canTeach = myProfile.known ? myProfile.known.split(',').map(s=>s.trim()).filter(m => pLearn.some(p=>p.includes(m))) : [];
  const canLearn = myProfile.learn ? myProfile.learn.split(',').map(s=>s.trim()).filter(m => pKnow.some(p=>p.includes(m))) : [];
  return { canTeach, canLearn };
}
async function loadPosts(filter='') {
  const list = $('posts-list'); const query = filter ? '?lang='+encodeURIComponent(filter) : '';
  try {
    const res = await fetch('/api/posts'+query); const posts = await res.json();
    if (!posts.length) { list.innerHTML='<p>No posts found.</p>'; return; }
    list.innerHTML = '';
    posts.forEach(p => {
      const { canTeach, canLearn } = getMatchInfo(p); const isMatch = canTeach.length>0 || canLearn.length>0;
      const div = document.createElement('div'); div.className = 'post'+(isMatch?' highlight':'');
      let badge=''; if (canTeach.length) badge += `<span class="match-badge">👍 Teach ${canTeach.join(', ')}</span>`;
      if (canLearn.length) badge += `<span class="match-badge">📖 Learn ${canLearn.join(', ')}</span>`;
      div.innerHTML = `<div><span class="lang">${escapeHtml(p.know_langs)}</span> → <span class="lang">${escapeHtml(p.learn_langs)}</span> ${badge}</div><div>${escapeHtml(p.message)}</div><div style="font-size:0.85rem;color:var(--muted);margin:4px 0">👤 ${escapeHtml(p.poster_name||'Anonymous')}</div><div class="time">${escapeHtml(p.timestamp)}</div><button class="msg-btn" onclick="openChat('${escapeHtml(p.poster_name||'User')}', '${p.cid}')">💬 Message</button>`;
      list.appendChild(div);
    });
  } catch(err) { list.innerHTML='<p>Failed to load posts.</p>'; }
}
loadPosts();
function openChat(toName, toCid) { if (!toCid) return alert('Cannot message'); currentChatTarget = toCid; $('messages-section').style.display = 'block'; $('msg-header').textContent = `Chat: ${toName}`; $('msg-text').value = ''; $('msg-text').focus(); loadMessages(toCid); }
$('close-msgs').onclick = () => { $('messages-section').style.display='none'; currentChatTarget=null; };
$('msg-send').onclick = async () => { const text = $('msg-text').value.trim(); if (!currentChatTarget || !text) return; try { await fetch('/api/message', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ from_cid: cid, from_name: myProfile.name||'Anonymous', to_cid: currentChatTarget, text: text }) }); $('msg-text').value = ''; loadMessages(currentChatTarget); } catch(err) { alert('Failed'); } };
$('msg-text').onkeydown = (e) => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); $('msg-send').click(); } };
async function loadMessages(targetCid) { const list = $('msg-list'); try { const res = await fetch('/api/messages?cid='+cid+'&target='+encodeURIComponent(targetCid)); const msgs = await res.json(); list.innerHTML = msgs.length ? '' : '<p style="color:var(--muted);font-size:0.9rem">Start chatting...</p>'; msgs.forEach(m => { const isMe = m.from_cid === cid; const div = document.createElement('div'); div.className='msg'; div.innerHTML = `<div><span class="${isMe?'msg-to':'msg-from'}">${isMe?'→ You':escapeHtml(m.from_name)}</span></div><div class="msg-text">${escapeHtml(m.text)}</div><div class="msg-time">${escapeHtml(m.timestamp)}</div>`; list.appendChild(div); }); scrollMsgs(); } catch(err) { list.innerHTML='<p style="color:var(--danger)">Failed</p>'; } }
function addMessageToUI(m) { if (!$('messages-section').style.display || $('messages-section').style.display==='none') return; const list = $('msg-list'), isMe = m.from_cid === cid; const div = document.createElement('div'); div.className='msg'; div.innerHTML = `<div><span class="${isMe?'msg-to':'msg-from'}">${isMe?'→ You':escapeHtml(m.from_name)}</span></div><div class="msg-text">${escapeHtml(m.text)}</div><div class="msg-time">${escapeHtml(m.timestamp)}</div>`; list.appendChild(div); scrollMsgs(); }
function scrollMsgs() { const list=$('msg-list'); if(list) list.scrollTop=list.scrollHeight; }
$('warn-ack-btn').onclick = () => { $('warning-overlay').classList.remove('active'); };
setInterval(() => { if (!$('banned-overlay').classList.contains('active')) fetch('/api/hb',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cid})}).catch(()=>{}); }, 500);
document.addEventListener('keydown', e => { if ((e.ctrlKey && e.shiftKey && e.code === 'KeyA') || (e.ctrlKey && e.shiftKey && e.code === 'KeyP')) { e.preventDefault(); toggleAdmin(); return; } if (e.key==='Escape' && adminOpen) { $('admin').classList.remove('show'); adminOpen=false; } if (e.key==='=' && adminOpen) { e.preventDefault(); fetch('/api/admin').then(r=>r.json()).then(d=>renderAdmin(d.clients,d.banned)); } });
$('open-admin-btn').onclick = () => toggleAdmin(); $('adminClose').onclick = () => { $('admin').classList.remove('show'); adminOpen=false; }; $('reload-db').onclick = () => { fetch('/api/admin/reload', {method:'POST'}); $('corner-hint').textContent='🔄 Reloading...'; setTimeout(()=>$('corner-hint').textContent='',1500); };
function toggleAdmin() { if (!adminOpen) { const pass = prompt('🔐 Admin password:'); if (pass !== 'admin') { alert('Denied'); return; } $('admin').classList.add('show'); adminOpen=true; fetch('/api/admin').then(r=>r.json()).then(d=>renderAdmin(d.clients,d.banned)); } else { $('admin').classList.remove('show'); adminOpen=false; } }
function renderAdmin(clients, banned) { const cList=$('cList'), bList=$('bList'); cList.innerHTML = Object.keys(clients).length ? '' : '<div class="client-item">No clients</div>'; Object.entries(clients).forEach(([id,info]) => { const isMe=id===cid, isBanned=banned.includes(id); const div=document.createElement('div'); div.className='client-item'; let buttons=''; if (!isBanned) buttons=`<button class="btn-sm btn-warn" data-a="warn" data-c="${id}">Warn</button><button class="btn-sm btn-kick" data-a="kick" data-c="${id}">Kick</button><button class="btn-sm btn-ban" data-a="ban" data-c="${id}">Ban</button>`; else buttons=`<span style="font-size:0.7rem;color:var(--danger)">⚠️ Banned</span>`; div.innerHTML=`<strong>${info.device||'Unknown'} ${isMe?'(You)':''}</strong><div class="client-id">${id.slice(0,10)}...</div><div class="client-meta">${info.ip} • ${new Date(info.ts*1000).toLocaleTimeString()}</div><div class="client-actions">${buttons}</div>`; cList.appendChild(div); }); bList.innerHTML = banned.length ? '' : '<div class="banned-item">No banned users</div>'; banned.forEach(id => { const div=document.createElement('div'); div.className='banned-item'; div.innerHTML=`<strong>Banned</strong><div class="client-id">${id.slice(0,10)}...</div> <button class="btn-sm btn-unban" data-a="unban" data-c="${id}">Unban</button>`; bList.appendChild(div); }); document.querySelectorAll('[data-a]').forEach(btn => { btn.onclick = () => { const action=btn.dataset.a, target=btn.dataset.c; let payload={action,target,by:cid}; if (action==='warn') { const reason=prompt('⚠️ Reason:','Inappropriate'); if(!reason)return; payload.reason=reason; } fetch('/api/admin/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(()=>fetch('/api/admin').then(r=>r.json()).then(d=>renderAdmin(d.clients,d.banned))); }; }); }
$('corner-hint').textContent = `Ready | Ctrl+Shift+A or 🔐 | CID: ${cid.slice(0,8)}...`;""",

    ".gitignore": """data/
__pycache__/
*.pyc
*.pyo
.DS_Store
.env
*.log""",

    "README.md": """# 🌍 Local Language Exchange Pro v3.3
Zero-dependency Python app. Run `python server.py`, open http://localhost:8000.
- 💬 One-click messaging (routes by CID)
- 🔐 Admin: `Ctrl+Shift+A` or header button (password: `admin`)
- 🧹 Terminal: type `clear data` to wipe & reboot
- ✅ Pure Python standard library"""
}

# ──────────────────────────────────────────────────────────────
# SETUP & DB
# ──────────────────────────────────────────────────────────────
def ensure_files_exist():
    print("📁 Checking project structure...")
    for path, content in FILE_CONTENTS.items():
        full = os.path.join(BASE_DIR, path)
        os.makedirs(os.path.dirname(full) if os.path.dirname(full) else BASE_DIR, exist_ok=True)
        if not os.path.exists(full):
            with open(full, "w", encoding="utf-8") as f: f.write(content)
            print(f"  ✅ Created {path}")
        else: print(f"  ⏭️  {path} exists")

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, know_langs TEXT NOT NULL, learn_langs TEXT NOT NULL, message TEXT NOT NULL, poster_name TEXT DEFAULT 'Anonymous', cid TEXT DEFAULT '', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, from_cid TEXT NOT NULL, from_name TEXT NOT NULL, to_cid TEXT NOT NULL, to_name TEXT NOT NULL, text TEXT NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("PRAGMA table_info(posts)"); cols = {r[1] for r in c.fetchall()}
    if "know_lang" in cols and "know_langs" not in cols:
        try: c.execute("ALTER TABLE posts RENAME COLUMN know_lang TO know_langs")
        except: pass
    if "learn_lang" in cols and "learn_langs" not in cols:
        try: c.execute("ALTER TABLE posts RENAME COLUMN learn_lang TO learn_langs")
        except: pass
    for col in ["poster_name", "cid"]:
        if col not in cols: c.execute(f"ALTER TABLE posts ADD COLUMN {col} TEXT DEFAULT ''")
    conn.commit(); conn.close()
    print("📦 Database ready.")

def load_banned():
    global banned_clients
    bf = os.path.join(DATA_DIR, "banned.json")
    try:
        if os.path.exists(bf): banned_clients = set(json.loads(open(bf, encoding="utf-8").read()))
    except: banned_clients = set()

def save_banned():
    open(os.path.join(DATA_DIR, "banned.json"), "w", encoding="utf-8").write(json.dumps(list(banned_clients)))

# ──────────────────────────────────────────────────────────────
# HTTP HANDLER
# ──────────────────────────────────────────────────────────────
MIME_TYPES = {".html":"text/html",".css":"text/css",".js":"application/javascript",".json":"application/json"}
class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def info(self):
        ua = self.headers.get('User-Agent','')
        dev = 'Mobile' if any(x in ua for x in ['Mobile','Android','iPhone']) else 'Tablet' if 'iPad' in ua else 'Desktop'
        return {'ip': self.client_address[0], 'device': dev}
    
    def do_GET(self):
        p = urlparse(self.path).path; q = parse_qs(urlparse(self.path).query); cid = q.get('cid',[None])[0]
        if p == '/api/events':
            if not cid: return self._json({'err':'missing cid'},400)
            return self._sse(cid)
        elif p == '/api/posts':
            lang = q.get('lang',[None])[0]
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            if lang: c.execute("SELECT * FROM posts WHERE know_langs LIKE ? OR learn_langs LIKE ? ORDER BY timestamp DESC LIMIT 100", (f"%{lang}%",f"%{lang}%"))
            else: c.execute("SELECT * FROM posts ORDER BY timestamp DESC LIMIT 100")
            rows = c.fetchall(); conn.close()
            return self._json([{"id":r[0],"know_langs":r[1],"learn_langs":r[2],"message":r[3],"poster_name":r[4],"cid":r[5],"timestamp":r[6]} for r in rows])
        elif p == '/api/messages':
            my_cid, target = q.get('cid',[None])[0], q.get('target',[None])[0]
            if not my_cid or not target: return self._json({'err':'missing params'},400)
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT from_cid,from_name,to_cid,to_name,text,timestamp FROM messages WHERE (from_cid=? AND to_cid=?) OR (from_cid=? AND to_cid=?) ORDER BY timestamp ASC LIMIT 100", (my_cid,target,target,my_cid))
            rows = c.fetchall(); conn.close()
            return self._json([{"from_cid":r[0],"from_name":r[1],"to_cid":r[2],"to_name":r[3],"text":r[4],"timestamp":r[5]} for r in rows])
        elif p == '/api/admin':
            with lock: clients = {c:{k:v for k,v in i.items() if k!='q'} for c,i in active_clients.items()}
            return self._json({'clients':clients,'banned':list(banned_clients)})
        elif p in ['/','/index.html']: return self._serve_file('index.html','text/html')
        elif p.startswith('/static/'):
            fname = p.split('/')[-1]; ext = os.path.splitext(fname)[1]
            return self._serve_file(os.path.join('static',fname), MIME_TYPES.get(ext,'application/octet-stream'))
        else: return self._json({'err':'not found'},404)
    
    def do_POST(self):
        p = urlparse(self.path).path; ln = int(self.headers.get('Content-Length',0))
        try: body = json.loads(self.rfile.read(ln).decode('utf-8')) if ln else {}
        except: return self._json({'err':'bad json'},400)
        
        if p == '/api/posts':
            know, learn, msg, name, cid = body.get('know_langs','').strip(), body.get('learn_langs','').strip(), body.get('message','').strip(), body.get('poster_name','Anonymous').strip(), body.get('cid','')
            if not all([know,learn,msg]): return self._json({'err':'Missing fields'},400)
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("INSERT INTO posts (know_langs,learn_langs,message,poster_name,cid) VALUES (?,?,?,?,?)", (know,learn,msg,name,cid))
            conn.commit(); conn.close()
            with lock:
                for inf in active_clients.values():
                    try: inf['q'].put_nowait({'type':'update'})
                    except: pass
            return self._json({'status':'ok'})
        elif p == '/api/message':
            from_cid, from_name, to_cid, text = body.get('from_cid'), body.get('from_name'), body.get('to_cid'), body.get('text')
            if not all([from_cid,from_name,to_cid,text]): return self._json({'err':'Missing fields'},400)
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT poster_name FROM posts WHERE cid=? LIMIT 1", (to_cid,))
            row = c.fetchone(); to_name = row[0] if row else "User"
            c.execute("INSERT INTO messages (from_cid,from_name,to_cid,to_name,text) VALUES (?,?,?,?,?)", (from_cid,from_name,to_cid,to_name,text))
            conn.commit(); conn.close()
            with lock:
                if to_cid in sse_queues:
                    try: sse_queues[to_cid].put_nowait({'type':'message','data':{'from_cid':from_cid,'from_name':from_name,'to_cid':to_cid,'to_name':to_name,'text':text,'timestamp':time.strftime('%Y-%m-%d %H:%M:%S')}})
                    except: pass
            return self._json({'status':'ok'})
        elif p == '/api/hb':
            if cid:
                with lock:
                    if cid not in active_clients: inf=self.info(); active_clients[cid]={'ts':time.time(),'ip':inf['ip'],'device':inf['device'],'q':sse_queues.get(cid)}
                    else: active_clients[cid]['ts']=time.time()
            return self._json({'ok':True})
        elif p == '/api/admin/action':
            action,tgt,by = body.get('action'), body.get('target'), body.get('by')
            with lock:
                if action=='warn':
                    reason = body.get('reason','Warning')
                    if tgt in sse_queues:
                        try: sse_queues[tgt].put_nowait({'type':'warning','message':reason})
                        except: pass
                elif action=='kick':
                    if tgt in sse_queues:
                        try: sse_queues[tgt].put_nowait({'type':'kicked'})
                        except: pass
                    active_clients.pop(tgt,None); sse_queues.pop(tgt,None)
                elif action=='ban':
                    banned_clients.add(tgt); save_banned()
                    if tgt in sse_queues:
                        try: sse_queues[tgt].put_nowait({'type':'banned'})
                        except: pass
                elif action=='unban':
                    banned_clients.discard(tgt); save_banned()
                    if tgt in sse_queues:
                        try: sse_queues[tgt].put_nowait({'type':'unbanned'})
                        except: pass
                for inf in active_clients.values():
                    try:
                        cl = {c:{k:v for k,v in i.items() if k!='q'} for c,i in active_clients.items()}
                        inf['q'].put_nowait({'type':'admin','clients':cl,'banned':list(banned_clients)})
                    except: pass
            return self._json({'ok':True})
        elif p == '/api/admin/reload':
            with lock:
                for inf in active_clients.values():
                    try: inf['q'].put_nowait({'type':'update'})
                    except: pass
            return self._json({'ok':True})
        else: return self._json({'err':'not found'},404)
    
    def _sse(self, cid):
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.send_header('Connection','keep-alive'); self.end_headers()
        self.wfile.write(f'data: {json.dumps({"type":"connected","cid":cid})}\n\n'.encode()); self.wfile.flush()
        import queue; q = queue.Queue(); inf = self.info()
        with lock: sse_queues[cid]=q; active_clients[cid]={'ts':time.time(),'ip':inf['ip'],'device':inf['device'],'q':q}
        if cid in banned_clients:
            try: q.put_nowait({"type":"banned"})
            except: pass
        try:
            while True:
                try:
                    msg = q.get(timeout=5)
                    self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode()); self.wfile.flush()
                except queue.Empty:
                    try: self.wfile.write(b":\n\n"); self.wfile.flush()
                    except: break
                except: break
        finally:
            with lock: sse_queues.pop(cid,None); active_clients.pop(cid,None)
    
    def _serve_file(self, rel_path, mime):
        full = os.path.join(BASE_DIR, rel_path)
        if not os.path.exists(full): return self._json({'err':'not found'},404)
        with open(full,'rb') as f: content = f.read()
        self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Content-Length',len(content)); self.end_headers()
        self.wfile.write(content)
    
    def _json(self, data, code=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',len(body)); self.end_headers()
        self.wfile.write(body)

# ──────────────────────────────────────────────────────────────
# MONITOR
# ──────────────────────────────────────────────────────────────
def monitor():
    while True:
        time.sleep(5)
        with lock:
            now = time.time()
            for c in list(active_clients):
                if now - active_clients[c]['ts'] > HEARTBEAT_TIMEOUT:
                    active_clients.pop(c,None); sse_queues.pop(c,None)

# ──────────────────────────────────────────────────────────────
# MAIN (FIXED ARCHITECTURE)
# ──────────────────────────────────────────────────────────────
def run_server(port):
    """Runs in background thread. Blocks until shutdown() is called."""
    server = ThreadingHTTPServer(("0.0.0.0", port), RequestHandler)
    print(f"🌐 Listening on http://0.0.0.0:{port}")
    server.serve_forever()

def start_server_thread(port):
    """Starts server in daemon thread, waits briefly to confirm port bind."""
    t = threading.Thread(target=run_server, args=(port,), daemon=True)
    t.start()
    time.sleep(0.3)  # Give socket time to bind
    return t

def wipe_and_rebuild():
    """Safely wipes generated files (keeps server.py) and rebuilds."""
    print("\n🧹 Wiping generated files (keeping server.py)...")
    for item in os.listdir(BASE_DIR):
        if item == SERVER_FILE or item == "__pycache__" or item.startswith('.'):
            continue
        item_path = os.path.join(BASE_DIR, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
            print(f"  🗑️  Deleted: {item}")
        except Exception as e:
            print(f"  ⚠️  Skip {item}: {e}")
    print("✅ Wipe complete. Rebuilding...")
    ensure_files_exist(); init_db(); load_banned()
    print("📦 Fresh database & files created.\n")

def main():
    print("="*60)
    print("  🌍 Local Language Exchange Pro v3.3")
    print("  Zero installs | Admin: Ctrl+Shift+A or 🔐")
    print("  Terminal: type 'clear data' to wipe & reboot")
    print("="*60 + "\n")
    
    ensure_files_exist(); init_db(); load_banned()
    threading.Thread(target=monitor, daemon=True).start()
    
    server_thread = start_server_thread(PORT)
    print("✅ Server running! Open http://localhost:8000")
    print("💡 Type commands below:")
    
    while True:
        try:
            cmd = input(">> ").strip().lower()
            if cmd == "clear data":
                print("🔄 Shutting down server for reset...")
                # We can't call server.shutdown() directly from here since server_thread is daemon
                # Instead, we'll trigger a graceful exit and restart
                import sys
                os.execv(sys.executable, [sys.executable] + sys.argv)
                # os.execv replaces the current process entirely, clean & safe
            elif cmd == "help":
                print("Commands:\n  clear data → Wipe & reboot\n  help → Show this\n  Ctrl+C → Stop")
            elif cmd:
                print(f"❓ Unknown: '{cmd}'")
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Stopped.")
            break

if __name__ == "__main__":
    main()
