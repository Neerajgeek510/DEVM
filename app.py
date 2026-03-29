
from flask import Flask, render_template, request, redirect, session, send_from_directory, Response
import random, os, shutil, csv, io
from datetime import datetime, date
from dotenv import load_dotenv
import os
import psycopg2

load_dotenv()

app = Flask(__name__)



app.config['ADMIN_USER'] = os.getenv("ADMIN_USER")
app.config['ADMIN_PASS'] = os.getenv("ADMIN_PASS")
secret = os.getenv("SECRET_KEY")
if not secret:
    raise RuntimeError("SECRET_KEY  is missing 😅")
app.secret_key = secret
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").strip().lower() == "true"
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_APP_PASSWORD = os.getenv("SENDER_APP_PASSWORD")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER = os.path.join(BASE_DIR, "pdfs")
SENT_PDFS = os.path.join(BASE_DIR, "sent_pdfs")
os.makedirs(PDF_FOLDER, exist_ok=True)
os.makedirs(SENT_PDFS, exist_ok=True)


CANDIDATE_PDFS = {
    "Maharana Pratap": "maharana_pratap.pdf",
    "Chandrashekhar Aazad": "chandrashekhar_azad.pdf",
    "Bhagat Singh": "bhagat_singh.pdf",
    "Chhatrapati Shivaji Maharaj": "shivaji_maharaj.pdf"
}


DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)
@app.route("/")
def home():
     return render_template("home.html")
# @app.route("/index")
# def index():
#     return render_template("index.html")

def age_from_dob(dob_str):
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

import requests

def send_otp_email(email, otp):
    if not EMAIL_ENABLED:
        print(f"[DEMO] OTP for {email}: {otp}")
        return True

    try:
        url = "https://api.brevo.com/v3/smtp/email"

        headers = {
            "accept": "application/json",
            "api-key": os.getenv("BREVO_API_KEY"),
            "content-type": "application/json"
        }

        data = {
            "sender": {
                "name": "DEVM E-Voting",
                "email": "ninjaxcoder89@gmail.com"
            },
            "to": [
                {"email": email}
            ],
            "subject": "DEVM E-Voting OTP",
            "htmlContent": f"<h2>Your OTP is: {otp}</h2>"
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 201:
            print("OTP sent via Brevo ✅")
            return True
        else:
            print("Brevo error:", response.text)
            return False

    except Exception as e:
        print("Brevo exception:", e)
        return False



import base64
def send_pdf_email_or_copy(email, pdf_filename):
    pdf_path = os.path.join(PDF_FOLDER, pdf_filename)

    if not os.path.isfile(pdf_path):
        print("PDF not found:", pdf_path)
        return False

    try:
        # read and encode pdf
        with open(pdf_path, "rb") as f:
            encoded_file = base64.b64encode(f.read()).decode()

        url = "https://api.brevo.com/v3/smtp/email"

        headers = {
            "accept": "application/json",
            "api-key": os.getenv("BREVO_API_KEY"),
            "content-type": "application/json"
        }

        data = {
            "sender": {
                "name": "DEVM E-Voting",
                "email": "ninjaxcoder89@gmail.com"
            },
            "to": [
                {"email": email}
            ],
            "subject": "Thanks for Voting 🗳️",
            "htmlContent": "<h3>Thank you for voting! Your candidate manifesto is attached.</h3>",
            "attachment": [
                {
                    "content": encoded_file,
                    "name": pdf_filename
                }
            ]
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 201:
            print("PDF sent via Brevo ✅")
            return True
        else:
            print("Brevo PDF error:", response.text)
            return False

    except Exception as e:
        print("PDF exception:", e)
        return False

# ---------- ROUTES ----------

# INDEX: form + inline OTP area (action=send_otp)
@app.route("/index", methods=["GET","POST"]) 
def index():
    if request.method == "POST":
        action = request.form.get("action", "send_otp")
        if action == "send_otp":
            email = request.form.get("email")
            dob = request.form.get("dob")
            aadhaar = request.form.get("aadhaar")
            if not email or not dob or not aadhaar:
                return render_template("index.html", error="Please fill all fields.")
            if not aadhaar.isdigit() or len(aadhaar) != 12:
                return render_template("index.html", error="Aadhaar must be 12 digits.")
            if age_from_dob(dob) < 18:
                return render_template("index.html", error="You must be 18 or older to vote.")
            # store in session and send OTP
            otp = str(random.randint(100000, 999999))
            session["otp"] = otp
            session["email"] = email
            session["aadhaar"] = aadhaar
            ok = send_otp_email(email, otp)
            if not ok:
                return render_template("index.html", error="Failed to send OTP. Check server logs or SMTP config.")
            return render_template("index.html", otp_sent=True, email=email)
    return render_template("index.html")

# verify OTP (POST from index)
@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    user_otp = request.form.get("otp")
    if user_otp and session.get("otp") and user_otp == session.get("otp"):
        session.pop("otp", None)
        return redirect("/vote")
    return render_template("index.html", otp_sent=True, error="Invalid OTP, try again.", email=session.get("email"))

# Vote page
# REPLACE your existing /vote route with this block in app.py
import psycopg2
from psycopg2 import errors
import traceback

@app.route("/vote", methods=["GET","POST"])
def vote():
    if request.method == "POST":
        print("==== DEBUG /vote POST START ====")
        try:
            print("FORM KEYS:", list(request.form.keys()))
            for k in request.form.keys():
                print("  ", k, "=", request.form.get(k))

            candidate = request.form.get("candidate")
            print("DEBUG: candidate from form:", candidate)

            # show all session keys for debug
            print("DEBUG: session keys:", {k: session.get(k) for k in ("email","aadhaar")})

            if not candidate:
                print("ERROR: candidate missing")
                return "Candidate missing", 400

            # get email/aadhaar from session (fall back to demo values but log)
            email = session.get("email")
            aadhaar = session.get("aadhaar")
            if not email or not aadhaar:
                print("WARNING: session email/aadhaar missing. Using demo fallback values.")
                email = email or "voice_user_demo@example.com"
                aadhaar = aadhaar or "000000000000"

            timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

            # Try DB insert with explicit logging and exception handling
            con = get_db()
            cur = con.cursor()
            try:
                cur.execute("INSERT INTO votes(email,aadhaar,candidate,time) VALUES(%s,%s,%s,%s)",
                            (email, aadhaar, candidate, timestamp))
                con.commit()
                print("DEBUG: DB insert SUCCESS")
            except errors.UniqueViolation as e:
                con.rollback()
                print("DB IntegrityError (probably duplicate aadhaar):", e)
                con.close()
                # render vote.html with message
                return render_template("vote.html", error="This Aadhaar has already voted.", candidates=list(CANDIDATE_PDFS.keys()))
            except Exception as e:
                con.rollback()
                print("DB insert exception:", e)
                traceback.print_exc()
                con.close()
                return render_template("vote.html", error="Database error. See server logs.", candidates=list(CANDIDATE_PDFS.keys()))
            con.close()

            # now send pdf  and log result
            pdffile = CANDIDATE_PDFS.get(candidate)
            pdf_result = False
            if pdffile:
                try:
                    pdf_result = send_pdf_email_or_copy(email, pdffile)
                    print("PDF send/copy result:", pdf_result)
                except Exception as e:
                    print("PDF send/copy exception:", e)
                    traceback.print_exc()

            print("==== DEBUG /vote POST END ====")
            return render_template("success.html", candidate=candidate)

        except Exception as e:
            print("Unhandled exception in /vote:")
            traceback.print_exc()
            return "Server error (see logs)", 500

  
    
    return render_template("vote.html", candidates=list(CANDIDATE_PDFS.keys()))   
# @app.route("/download_db")
# def download_db():
#     return send_from_directory(os.path.dirname(DB_PATH), "database.db", as_attachment=True)

# ---------- ADMIN ----------
@app.route("/admin_login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username")
        pw = request.form.get("password")
        if user == app.config['ADMIN_USER'] and pw == app.config['ADMIN_PASS']:
            session['admin'] = True
            return redirect("/admin")
        return render_template("admin_login.html", error="Invalid username or password")
    return render_template("admin_login.html")

@app.route("/admin")
def admin():
    if not session.get('admin'):
        return redirect("/admin_login")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT email,aadhaar,candidate,time FROM votes ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    # mask aadhaar for display
    data = [(e, ("XXXX-XXXX-" + (a[-4:] if a and len(a) >= 4 else a)), c, t) for (e, a, c, t) in rows]
    # counts
    counts = {}
    for _, _, cand, _ in rows:
        counts[cand] = counts.get(cand, 0) + 1
    return render_template("admin.html", data=data, counts=counts)

@app.route("/admin/download_csv")
def admin_download_csv():
    if not session.get('admin'):
        return redirect("/admin_login")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT email,aadhaar,candidate,time FROM votes ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['email', 'aadhaar_masked', 'candidate', 'time'])
    for e, a, c, t in rows:
        masked = "XXXX-XXXX-" + (a[-4:] if a and len(a) >= 4 else a)
        cw.writerow([e, masked, c, t])
    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=votes.csv"})

@app.route("/admin/logout")
def admin_logout():
    session.pop('admin', None)
    return redirect("/admin_login")

# serve PDFs for browser view (optional)
@app.route("/pdfs/<path:filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_FOLDER, filename, as_attachment=False)
@app.route("/initdb")
def initdb():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        id SERIAL PRIMARY KEY,
        email TEXT,
        aadhaar TEXT UNIQUE,
        candidate TEXT,
        time TEXT
    )
    """)
    con.commit()
    con.close()
    return "DB Ready"

# ---------- RUN ----------
if __name__ == "__main__":
    if EMAIL_ENABLED:
        print("EMAIL_ENABLED = True (SMTP active)")
    else:
        print("EMAIL_ENABLED = False (Demo mode)")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

