import os, json, sqlite3, hashlib, difflib, queue, threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session, send_from_directory, Response
from flask_cors import CORS

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'onboarding.db')
UPLOADS = os.path.join(BASE, 'uploads')
os.makedirs(UPLOADS, exist_ok=True)
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret-change-me')
CORS(app, supports_credentials=True, origins=['http://localhost:5173'])
subscribers = {}
lock = threading.Lock()

POLICIES = [
    ('Core Work Hours', 'Core work hours are 10:00 AM to 4:00 PM, Monday through Friday. Teams may set additional collaboration hours.'),
    ('Leave Policy', 'Employees request planned leave through the HR portal. Emergency leave should be communicated to the manager as soon as possible.'),
    ('Remote Work', 'Remote work is allowed according to the employee\'s team policy. Keep your calendar and status updated while working remotely.'),
    ('Information Security', 'Never share passwords or MFA codes. Use company-managed devices and report suspected security incidents to IT immediately.'),
    ('Harassment Prevention', 'All employees must complete harassment prevention training and achieve 100% on the compliance quiz before completion is recorded.'),
    ('NDA', 'Employees handling confidential company information must sign the NDA before accessing restricted systems or customer information.')
]

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

def init_db():
    con=db(); c=con.cursor()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,email TEXT UNIQUE,password TEXT,department TEXT,role TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,description TEXT,department TEXT,priority TEXT,due_day INTEGER,requires_quiz INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS user_tasks(user_id INTEGER,task_id INTEGER,completed INTEGER DEFAULT 0,completed_at TEXT,PRIMARY KEY(user_id,task_id));
    CREATE TABLE IF NOT EXISTS uploads(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,task_id INTEGER,filename TEXT,stored_name TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,role TEXT,message TEXT,created_at TEXT);
    ''')
    if c.execute('SELECT COUNT(*) n FROM users').fetchone()['n']==0:
        users=[('Alex Morgan','alex@company.com','password','Engineering','employee'),('Priya Shah','priya@company.com','password','Sales','employee'),('Samira Khan','samira@company.com','password','Design','employee'),('HR Admin','hr@company.com','admin123','HR','admin')]
        for u in users: c.execute('INSERT INTO users(name,email,password,department,role,created_at) VALUES(?,?,?,?,?,?)',(u[0],u[1],hash_pw(u[2]),u[3],u[4],datetime.utcnow().isoformat()))
    if c.execute('SELECT COUNT(*) n FROM tasks').fetchone()['n']==0:
        tasks=[
        ('Set up direct deposit','Add your bank details through the payroll portal.','General','High',1,0),
        ('Complete profile','Add your contact and emergency information.','General','Medium',1,0),
        ('Harassment Prevention Training','Complete the compliance training and score 100% on the quiz.','General','High',2,1),
        ('Sign NDA','Review and sign the employee confidentiality agreement.','General','High',1,0),
        ('Gain GitHub access','Request access to the company GitHub organization.','Engineering','High',1,0),
        ('Set up development environment','Install approved tools and clone the starter repository.','Engineering','Medium',2,0),
        ('Engineering Architecture Overview','Read the architecture guide and attend the technical overview.','Engineering','Medium',3,0),
        ('CRM Access','Request access to the sales CRM.','Sales','High',1,0),
        ('Sales Playbook Review','Review the sales playbook and qualification process.','Sales','Medium',2,0),
        ('Customer Introduction','Join a customer-facing call with your manager.','Sales','Low',4,0),
        ('Brand Guidelines Review','Review the latest brand guidelines.','Design','High',2,0),
        ('Design System Access','Request access to the design system workspace.','Design','Medium',1,0),
        ('Portfolio Orientation','Review active projects and design workflows.','Design','Low',4,0)]
        for t in tasks: c.execute('INSERT INTO tasks(title,description,department,priority,due_day,requires_quiz) VALUES(?,?,?,?,?,?)',t)
    con.commit(); con.close()
init_db()

def current_user():
    uid=session.get('uid')
    if not uid:return None
    con=db(); u=con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(); con.close(); return u

def assign_tasks(uid, dept):
    con=db(); rows=con.execute("SELECT id FROM tasks WHERE department='General' OR department=?",(dept,)).fetchall()
    for r in rows: con.execute('INSERT OR IGNORE INTO user_tasks(user_id,task_id) VALUES(?,?)',(uid,r['id']))
    con.commit(); con.close()

def user_payload(u): return {'id':u['id'],'name':u['name'],'email':u['email'],'department':u['department'],'role':u['role']}

@app.post('/api/login')
def login():
    data=request.json or {}; con=db(); u=con.execute('SELECT * FROM users WHERE email=? AND password=?',(data.get('email'),hash_pw(data.get('password','')))).fetchone(); con.close()
    if not u:return jsonify({'error':'Invalid email or password'}),401
    session['uid']=u['id']; assign_tasks(u['id'],u['department']); return jsonify({'user':user_payload(u)})

@app.post('/api/logout')
def logout(): session.clear(); return jsonify({'ok':True})

@app.get('/api/me')
def me():
    u=current_user(); return jsonify({'user':user_payload(u) if u else None})

@app.get('/api/tasks')
def tasks():
    u=current_user()
    if not u:return jsonify({'error':'Unauthorized'}),401
    assign_tasks(u['id'],u['department']); con=db(); rows=con.execute('''SELECT t.*,ut.completed,ut.completed_at FROM tasks t JOIN user_tasks ut ON t.id=ut.task_id WHERE ut.user_id=? ORDER BY ut.completed ASC,t.due_day ASC,t.priority DESC''',(u['id'],)).fetchall(); con.close()
    return jsonify({'tasks':[dict(r) for r in rows]})

@app.post('/api/tasks/<int:tid>/complete')
def complete(tid):
    u=current_user();
    if not u:return jsonify({'error':'Unauthorized'}),401
    con=db(); t=con.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
    if not t:return jsonify({'error':'Task not found'}),404
    if t['requires_quiz'] and (request.json or {}).get('quiz_score')!=100:return jsonify({'error':'A 100% quiz score is required.'}),400
    con.execute('UPDATE user_tasks SET completed=1,completed_at=? WHERE user_id=? AND task_id=?',(datetime.utcnow().isoformat(),u['id'],tid)); con.commit(); con.close(); return jsonify({'ok':True})

@app.post('/api/tasks/<int:tid>/upload')
def upload(tid):
    u=current_user();
    if not u:return jsonify({'error':'Unauthorized'}),401
    f=request.files.get('file')
    if not f:return jsonify({'error':'No file selected'}),400
    safe=os.path.basename(f.filename); stored=f'{u["id"]}_{int(datetime.utcnow().timestamp())}_{safe}'; f.save(os.path.join(UPLOADS,stored))
    con=db(); con.execute('INSERT INTO uploads(user_id,task_id,filename,stored_name,created_at) VALUES(?,?,?,?,?)',(u['id'],tid,safe,stored,datetime.utcnow().isoformat())); con.commit(); con.close(); return jsonify({'ok':True,'filename':safe})

@app.get('/api/uploads/<name>')
def dl(name): return send_from_directory(UPLOADS,name,as_attachment=True)

QUIZ=[
 {'q':'A colleague makes repeated unwelcome comments about another employee. What is the best response?','options':['Ignore it completely','Report it through the appropriate company channel','Share it on social media','Retaliate'], 'a':1},
 {'q':'You receive a suspicious attachment from an unknown sender. What should you do?','options':['Open it quickly','Forward it to everyone','Report it to IT/security without opening','Disable antivirus'], 'a':2},
 {'q':'Which score is required to complete the harassment prevention task?','options':['60%','75%','90%','100%'], 'a':3}
]
@app.get('/api/quiz')
def quiz(): return jsonify({'questions':[{k:v for k,v in q.items() if k!='a'} for q in QUIZ]})

@app.get('/api/admin/employees')
def employees():
    u=current_user();
    if not u or u['role']!='admin':return jsonify({'error':'Forbidden'}),403
    con=db(); users=con.execute("SELECT id,name,email,department FROM users WHERE role='employee'").fetchall(); out=[]
    for e in users:
        total=con.execute('SELECT COUNT(*) n FROM user_tasks WHERE user_id=?',(e['id'],)).fetchone()['n']; done=con.execute('SELECT COUNT(*) n FROM user_tasks WHERE user_id=? AND completed=1',(e['id'],)).fetchone()['n']; pending=con.execute('''SELECT t.title,t.priority,t.due_day FROM tasks t JOIN user_tasks ut ON t.id=ut.task_id WHERE ut.user_id=? AND ut.completed=0 ORDER BY t.due_day ASC''',(e['id'],)).fetchall(); out.append({'id':e['id'],'name':e['name'],'email':e['email'],'department':e['department'],'progress':round(done/total*100) if total else 0,'pending':[dict(x) for x in pending]})
    con.close(); return jsonify({'employees':out})

def publish(uid, payload):
    with lock:
        for q in subscribers.get(uid,[]): q.put(payload)

@app.post('/api/admin/reminder/<int:uid>')
def reminder(uid):
    u=current_user();
    if not u or u['role']!='admin':return jsonify({'error':'Forbidden'}),403
    con=db(); e=con.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone(); con.close()
    if not e:return jsonify({'error':'Employee not found'}),404
    publish(uid, {'type':'reminder','message':'Please check your pending high-priority onboarding items.'}); return jsonify({'ok':True})

@app.get('/api/events')
def events():
    u=current_user();
    if not u:return jsonify({'error':'Unauthorized'}),401
    q=queue.Queue()
    with lock: subscribers.setdefault(u['id'],[]).append(q)
    def stream():
        try:
            yield 'data: '+json.dumps({'type':'connected'})+'\n\n'
            while True:
                try: payload=q.get(timeout=20); yield 'data: '+json.dumps(payload)+'\n\n'
                except queue.Empty: yield ': keepalive\n\n'
        finally:
            with lock:
                if u['id'] in subscribers and q in subscribers[u['id']]: subscribers[u['id']].remove(q)
    return Response(stream(),mimetype='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/chat')
def chat():
    u=current_user();
    if not u:return jsonify({'error':'Unauthorized'}),401
    msg=(request.json or {}).get('message','').strip()
    if not msg:return jsonify({'error':'Message required'}),400
    con=db(); rows=con.execute('SELECT title,description,priority,due_day FROM tasks t JOIN user_tasks ut ON t.id=ut.task_id WHERE ut.user_id=? AND ut.completed=0 ORDER BY due_day ASC',(u['id'],)).fetchall(); con.close()
    if 'next' in msg.lower() or 'do next' in msg.lower():
        if rows:
            r=rows[0]; answer=f"As a {u['department']} employee, your next highest-priority pending task is '{r['title']}', due on Day {r['due_day']}. Open your onboarding checklist to complete it."
        else: answer='You have completed all assigned onboarding tasks. Great work.'
    else:
        terms=msg.lower().split(); best=None; score=0
        for title,text in POLICIES:
            s=difflib.SequenceMatcher(None,msg.lower(),(title+' '+text).lower()).ratio()
            overlap=len(set(terms)&set((title+' '+text).lower().split()))
            s+=overlap*.08
            if s>score:score=s;best=(title,text)
        if best and score>.25: answer=best[1]
        else: answer="I can help with onboarding policies, tasks, compliance, access, leave, security, and work hours. Try asking a specific question."
        key=os.getenv('OPENAI_API_KEY')
        if key:
            try:
                from openai import OpenAI
                client=OpenAI(api_key=key)
                context='\n'.join([f'{x}: {y}' for x,y in POLICIES])
                resp=client.responses.create(model=os.getenv('OPENAI_MODEL','gpt-4o-mini'),input=f'Answer the employee onboarding question using only this policy context. Be concise.\nPOLICIES:\n{context}\nQUESTION: {msg}')
                answer=resp.output_text
            except Exception: pass
    con=db(); con.execute('INSERT INTO chats(user_id,role,message,created_at) VALUES(?,?,?,?)',(u['id'],'user',msg,datetime.utcnow().isoformat())); con.execute('INSERT INTO chats(user_id,role,message,created_at) VALUES(?,?,?,?)',(u['id'],'assistant',answer,datetime.utcnow().isoformat())); con.commit(); con.close(); return jsonify({'answer':answer})

@app.get('/api/chat/history')
def history():
    u=current_user();
    if not u:return jsonify({'error':'Unauthorized'}),401
    con=db(); rows=con.execute('SELECT role,message,created_at FROM chats WHERE user_id=? ORDER BY id ASC',(u['id'],)).fetchall(); con.close(); return jsonify({'messages':[dict(r) for r in rows]})

if __name__=='__main__': app.run(port=5000,debug=True,threaded=True)
