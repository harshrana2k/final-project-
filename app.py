from  flask  import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import sqlite3, os, smtplib, uuid, io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = "securekey"
DB = "phishlab.db"
TRACK_PIXEL = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

# ---------- Database helpers ----------
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB):
        conn = get_db()
        cur = conn.cursor()
        cur.executescript(open("schema.sql").read())
        conn.commit()
        conn.close()

# ---------- Routes ----------
@app.route('/')
def index():
    conn = get_db()
    campaigns = conn.execute("SELECT * FROM campaigns").fetchall()
    return render_template('index.html', campaigns=campaigns)

@app.route('/create_campaign', methods=['GET', 'POST'])
def create_campaign():
    conn = get_db()
    templates = conn.execute("SELECT * FROM templates").fetchall()
    if request.method == 'POST':
        name = request.form['name']
        desc = request.form['description']
        sender_name = request.form['sender_name']
        sender_email = request.form['sender_email']
        template_id = request.form['template_id']
        conn.execute("INSERT INTO campaigns (name, description, sender_name, sender_email, template_id) VALUES (?,?,?,?,?)",
                     (name, desc, sender_name, sender_email, template_id))
        conn.commit()
        flash("Campaign created successfully!", "success")
        return redirect(url_for('index'))
    return render_template('create_campaign.html', templates=templates)

@app.route('/dashboard/<int:campaign_id>')
def dashboard(campaign_id):
    conn = get_db()
    campaign = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    events = conn.execute("""
        SELECT e.event_type, COUNT(*) AS count 
        FROM events e WHERE campaign_id=? GROUP BY e.event_type
    """, (campaign_id,)).fetchall()
    data = {e['event_type']: e['count'] for e in events}
    total_targets = conn.execute("SELECT COUNT(*) FROM targets WHERE campaign_id=?", (campaign_id,)).fetchone()[0]
    return render_template('dashboard.html', campaign=campaign, data=data, total_targets=total_targets)

@app.route('/send_test/<int:campaign_id>')
def send_test(campaign_id):
    conn = get_db()
    campaign = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    template = conn.execute("SELECT * FROM templates WHERE id=?", (campaign['template_id'],)).fetchone()
    test_email = "test@example.com"
    rid = str(uuid.uuid4())
    pixel_url = url_for('track', _external=True) + f"?cid={campaign_id}&rid={rid}"
    redirect_url = url_for('redirect_track', rid=rid, cid=campaign_id, _external=True)
    html_body = template['html_body'].replace('{{name}}', 'Test User').replace('{{link}}', redirect_url).replace('{{pixel}}', pixel_url)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = template['subject']
    msg['From'] = f"{campaign['sender_name']} <{campaign['sender_email']}>"
    msg['To'] = test_email
    msg.attach(MIMEText(html_body, 'html'))

    try:
        smtp = smtplib.SMTP('localhost', 1025)
        smtp.sendmail(campaign['sender_email'], [test_email], msg.as_string())
        smtp.quit()
        flash("Test email sent successfully! (Check MailHog)", "success")
    except Exception as e:
        flash(f"Error sending email: {e}", "danger")

    return redirect(url_for('index'))

# ---------- Tracking ----------
@app.route('/track')
def track():
    cid = request.args.get('cid')
    rid = request.args.get('rid')
    ip = request.remote_addr
    ua = request.headers.get('User-Agent')
    conn = get_db()
    conn.execute("INSERT INTO events (campaign_id, event_type, ip, user_agent) VALUES (?, 'open', ?, ?)", (cid, ip, ua))
    conn.commit()
    return send_file(io.BytesIO(TRACK_PIXEL), mimetype='image/gif')

@app.route('/r/<rid>')
def redirect_track(rid):
    cid = request.args.get('cid')
    ip = request.remote_addr
    ua = request.headers.get('User-Agent')
    conn = get_db()
    conn.execute("INSERT INTO events (campaign_id, event_type, ip, user_agent, url) VALUES (?, 'click', ?, ?, ?)",
                 (cid, ip, ua, request.url))
    conn.commit()
    return "<h2>This is a simulated phishing landing page for training only.</h2>"

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
