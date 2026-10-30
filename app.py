import os, sqlite3, secrets, time
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, render_template, redirect, url_for, session, flash, abort
import requests

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DB=os.environ.get("DATABASE_PATH","data.db")
WEBHOOK=os.environ.get("DISCORD_WEBHOOK_URL","")
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","")
os.makedirs(os.path.dirname(DB) or ".",exist_ok=True)

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    return c
def init():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS appeals(id INTEGER PRIMARY KEY AUTOINCREMENT,created TEXT,discord TEXT,discord_id TEXT,roblox TEXT,roblox_id TEXT,reason TEXT,explanation TEXT,why TEXT,evidence TEXT,status TEXT DEFAULT 'En attente',ip TEXT,user_agent TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY AUTOINCREMENT,created TEXT,ip TEXT,path TEXT,user_agent TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS bans(ip TEXT PRIMARY KEY,created TEXT,reason TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS attempts(ip TEXT,stamp INTEGER)""")
init()

def client_ip():
    # Adresse vue par Flask ; ne pas accepter un en-tête fourni librement par le visiteur.
    return request.remote_addr or "inconnu"

def notify_visit(ip, path, user_agent, created):
    """Envoie une alerte de sécurité minimale au webhook privé configuré."""
    if not WEBHOOK:
        return
    embed = {
        "title": "Nouvelle visite du site",
        "color": 0x8B5CF6,
        "fields": [
            {"name": "Adresse IP", "value": str(ip)[:100], "inline": True},
            {"name": "Date (UTC)", "value": str(created)[:80], "inline": True},
            {"name": "Page", "value": str(path)[:500], "inline": False},
            {"name": "Navigateur", "value": str(user_agent or "Inconnu")[:250], "inline": False},
        ],
        "footer": {"text": "Journal de sécurité • conservation limitée"}
    }
    try:
        requests.post(WEBHOOK, json={"embeds": [embed]}, timeout=4).raise_for_status()
    except requests.RequestException:
        app.logger.exception("Discord visit webhook failed")

def blocked(ip):
    with db() as c: return c.execute("SELECT 1 FROM bans WHERE ip=?",(ip,)).fetchone() is not None
@app.before_request
def track():
    ip=client_ip()
    if blocked(ip): abort(403)
    if request.endpoint not in ("static", "health"):
        created = datetime.now(timezone.utc).isoformat()
        ua = request.user_agent.string[:250]
        with db() as c:
            c.execute("INSERT INTO visits(created,ip,path,user_agent) VALUES(?,?,?,?)",(created,ip,request.path,ua))
            # Les journaux de visites sont automatiquement supprimés après 30 jours.
            c.execute("DELETE FROM visits WHERE created < ?", ((datetime.now(timezone.utc) - __import__("datetime").timedelta(days=30)).isoformat(),))
        notify_visit(ip, request.path, ua, created)
def rate_ok(ip):
    now=int(time.time())
    with db() as c:
        c.execute("DELETE FROM attempts WHERE stamp<?",(now-3600,))
        n=c.execute("SELECT COUNT(*) FROM attempts WHERE ip=? AND stamp>?",(ip,now-3600)).fetchone()[0]
        if n>=5: return False
        c.execute("INSERT INTO attempts(ip,stamp) VALUES(?,?)",(ip,now))
    return True
def admin_required(fn):
    @wraps(fn)
    def inner(*a,**kw):
        if not session.get("admin"): return redirect(url_for("login"))
        return fn(*a,**kw)
    return inner

@app.get("/")
def index():
    return render_template("index.html")
@app.post("/appeal")
def appeal():
    ip=client_ip()
    if not rate_ok(ip):
        flash("Trop de demandes. Réessaie dans un moment.","error"); return redirect(url_for("index"))
    fields={k:request.form.get(k,"").strip() for k in ("discord","discord_id","roblox","roblox_id","reason","explanation","why","evidence")}
    if any(not fields[k] for k in ("discord","discord_id","roblox","roblox_id","reason","explanation","why")):
        flash("Merci de remplir tous les champs obligatoires.","error"); return redirect(url_for("index"))
    if len(fields["explanation"])>3000 or len(fields["why"])>2000: abort(400)
    created=datetime.now(timezone.utc).isoformat()
    with db() as c:
        cur=c.execute("""INSERT INTO appeals(created,discord,discord_id,roblox,roblox_id,reason,explanation,why,evidence,ip,user_agent) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(created,fields["discord"],fields["discord_id"],fields["roblox"],fields["roblox_id"],fields["reason"],fields["explanation"],fields["why"],fields["evidence"],ip,request.user_agent.string[:250]))
        appeal_id=cur.lastrowid
    if WEBHOOK:
        embed={"title":f"Nouvelle demande de débanissement #{appeal_id}","color":0x8B5CF6,"fields":[{"name":"Discord","value":fields["discord"]+" • "+fields["discord_id"],"inline":True},{"name":"Roblox","value":fields["roblox"]+" • "+fields["roblox_id"],"inline":True},{"name":"Motif du ban","value":fields["reason"][:1000],"inline":False},{"name":"Explications","value":fields["explanation"][:1000],"inline":False},{"name":"Pourquoi un débanissement ?","value":fields["why"][:1000],"inline":False},{"name":"Preuve / lien","value":fields["evidence"][:500] or "Aucune","inline":False}]}
        try: requests.post(WEBHOOK,json={"embeds":[embed]},timeout=8).raise_for_status()
        except requests.RequestException: app.logger.exception("Discord webhook failed")
    flash("Ta demande a bien été enregistrée. Elle sera étudiée par l'équipe.","success")
    return redirect(url_for("index"))

@app.route("/admin/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        if ADMIN_PASSWORD and secrets.compare_digest(request.form.get("password",""),ADMIN_PASSWORD):
            session.clear(); session["admin"]=True; return redirect(url_for("dashboard"))
        flash("Mot de passe incorrect.","error")
    return render_template("login.html")
@app.get("/admin/logout")
def logout():
    session.clear(); return redirect(url_for("index"))
@app.get("/admin")
@admin_required
def dashboard():
    with db() as c:
        appeals=c.execute("SELECT * FROM appeals ORDER BY id DESC LIMIT 100").fetchall()
        visits=c.execute("SELECT * FROM visits ORDER BY id DESC LIMIT 100").fetchall()
        bans=c.execute("SELECT * FROM bans ORDER BY created DESC").fetchall()
        count=c.execute("SELECT COUNT(*) FROM appeals").fetchone()[0]
    return render_template("admin.html",appeals=appeals,visits=visits,bans=bans,count=count)
@app.post("/admin/status/<int:appeal_id>")
@admin_required
def status(appeal_id):
    value=request.form.get("status","En attente")
    if value not in ("En attente","Acceptée","Refusée"): abort(400)
    with db() as c: c.execute("UPDATE appeals SET status=? WHERE id=?",(value,appeal_id))
    return redirect(url_for("dashboard"))
@app.post("/admin/ban")
@admin_required
def ban():
    ip=request.form.get("ip","").strip(); reason=request.form.get("reason","Blocage manuel")[:200]
    if ip:
        with db() as c: c.execute("INSERT OR REPLACE INTO bans(ip,created,reason) VALUES(?,?,?)",(ip,datetime.now(timezone.utc).isoformat(),reason))
    return redirect(url_for("dashboard"))
@app.post("/admin/unban")
@admin_required
def unban():
    with db() as c: c.execute("DELETE FROM bans WHERE ip=?",(request.form.get("ip",""),))
    return redirect(url_for("dashboard"))
@app.get("/health")
def health(): return {"status":"ok"}
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
