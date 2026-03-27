
from flask import Flask, render_template, request, redirect, session, send_from_directory, Response
import sqlite3, random, os, shutil, csv, io
from datetime import datetime, date
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import os

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


DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "database.db"))

def get_db():
    return sqlite3.connect(DB_PATH)
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

def send_otp_email(email, otp):
    if not EMAIL_ENABLED:
        print(f"[DEMO] OTP for {email}: {otp}")
        return True

    if not SENDER_EMAIL or not SENDER_APP_PASSWORD:
        print("SMTP credentials missing")
        return False

    try:
        msg = EmailMessage()
        msg.set_content(f"Your OTP for DEVM E-Voting is: {otp}")
        msg["Subject"] = "DEVM E-Voting OTP"
        msg["From"] = SENDER_EMAIL
        msg["To"] = email

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.send_message(msg)

        print(f"[EMAIL] OTP sent to {email}")
        return True

    except Exception as e:
        print("OTP email error:", repr(e))
        return False

def send_pdf_email_or_copy(email, pdf_filename):
    """
    Tries to send the PDF by email (if EMAIL_ENABLED True).
    If sending fails for any reason, falls back to copying the PDF into sent_pdfs/
    and returns False for email, True for copy.
    """
    pdf_path = os.path.join(PDF_FOLDER, pdf_filename)
    if not os.path.isfile(pdf_path):
        print("PDF not found:", pdf_path)
        return False

    # If email disabled -> demo copy
    if not EMAIL_ENABLED:
        dest = os.path.join(SENT_PDFS, f"{email}___{pdf_filename}")
        try:
            shutil.copyfile(pdf_path, dest)
            print(f"[DEMO] PDF copy saved to: {dest}")
            return True
        except Exception as e:
            print("Error copying PDF in demo mode:", e)
            return False

    # EMAIL_ENABLED == True: try sending via SMTP_SSL first (more reliable), then STARTTLS fallback
    try:
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()

        msg = EmailMessage()
        msg["Subject"] = "Candidate Manifesto - Thank you for voting"
        msg["From"] = SENDER_EMAIL
        msg["To"] = email
        msg.set_content("Thank you for voting. Attached is the candidate manifesto (PDF).")
        msg.add_attachment(pdf_data, maintype="application", subtype="pdf", filename=pdf_filename)

        # Try SMTP_SSL (port 465) first
        try:
            import smtplib
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.send_message(msg)
            server.quit()
            print(f"[EMAIL] PDF sent via SSL to {email}")
            return True
        except Exception as e_ssl:
            print("SMTP_SSL failed:", repr(e_ssl))
            # try STARTTLS fallback (port 587)
            try:
                server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
                server.ehlo()
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
                server.send_message(msg)
                server.quit()
                print(f"[EMAIL] PDF sent via STARTTLS to {email}")
                return True
            except Exception as e_tls:
                print("STARTTLS failed:", repr(e_tls))
                # fallback to demo copy
                dest = os.path.join(SENT_PDFS, f"{email}___{pdf_filename}")
                try:
                    shutil.copyfile(pdf_path, dest)
                    print(f"[FALLBACK] Email failed; PDF copied to: {dest}")
                    return False
                except Exception as e_copy:
                    print("Fallback copy also failed:", repr(e_copy))
                    return False

    except Exception as e:
        print("Unhandled exception in send_pdf_email_or_copy:", repr(e))
        try:
            dest = os.path.join(SENT_PDFS, f"{email}___{pdf_filename}")
            shutil.copyfile(pdf_path, dest)
            print(f"[FALLBACK] Exception -> copied to: {dest}")
            return False
        except Exception as e2:
            print("Fallback copy failed too:", repr(e2))
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
from sqlite3 import IntegrityError
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
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            try:
                cur.execute("INSERT INTO votes(email,aadhaar,candidate,time) VALUES(?,?,?,?)",
                            (email, aadhaar, candidate, timestamp))
                con.commit()
                print("DEBUG: DB insert SUCCESS")
            except IntegrityError as ie:
                con.rollback()
                print("DB IntegrityError (probably duplicate aadhaar):", ie)
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
    rows = cur.execute("SELECT email,aadhaar,candidate,time FROM votes ORDER BY id DESC").fetchall()
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
    rows = cur.execute("SELECT email,aadhaar,candidate,time FROM votes ORDER BY id DESC").fetchall()
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

# ---------- RUN ----------
if __name__ == "__main__":
    if EMAIL_ENABLED:
        print("EMAIL_ENABLED = True (SMTP active)")
    else:
        print("EMAIL_ENABLED = False (Demo mode)")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

