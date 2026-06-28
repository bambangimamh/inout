from flask import Flask, request, jsonify, render_template, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from models import db, Transaksi
import requests
import os
import time
import pandas as pd
import io
from zoneinfo import ZoneInfo
from itsdangerous import URLSafeTimedSerializer
from itsdangerous import BadSignature
from itsdangerous import SignatureExpired

app = Flask(__name__)

secret = os.getenv("SECRET_KEY")

if not secret:
    raise RuntimeError("SECRET_KEY belum diset.")

app.config["SECRET_KEY"] = secret

serializer = URLSafeTimedSerializer(
    app.config["SECRET_KEY"]
)

BASE_URL = "https://inout-production-88e5.up.railway.app"


def generate_dashboard_link(nomor_wa):

    token = serializer.dumps(nomor_wa)

    return f"{BASE_URL}/dashboard/{token}"


def verify_token(token):

    try:

        nomor = serializer.loads(
            token,
            max_age=60 * 60 * 24  # 1 hari
        )

        return nomor

    except (BadSignature, SignatureExpired):

        return None

# =========================
# CONFIG DB
# =========================
# app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///kas.db"
# ambil DATABASE_URL dari Railway
database_url = os.getenv("DATABASE_URL")

# FIX untuk Railway (postgres:// -> postgresql://)
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# ❗ INI WAJIB ADA
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    db.create_all()

def sekarang():
    return datetime.now(ZoneInfo("Asia/Jakarta"))

# =========================
# GLOBAL ANTI DUPLICATE
# =========================
PROCESSED = {}

def is_duplicate(msg_id):
    """Simple in-memory anti duplicate"""
    now = time.time()

    # bersihkan cache lama (10 menit)
    expired = [k for k, v in PROCESSED.items() if now - v > 600]
    for k in expired:
        del PROCESSED[k]

    if msg_id in PROCESSED:
        return True

    PROCESSED[msg_id] = now
    return False

@app.route("/dashboard/<token>")
def dashboard(token):

    nomor = verify_token(token)

    if not nomor:
        return "Link sudah tidak berlaku.", 403

    page = request.args.get("page", 1, type=int)

    per_page = 10

    query = Transaksi.query.filter(
        Transaksi.nomor_wa == nomor
    )

    data_paginated = query.order_by(
        Transaksi.tanggal.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    all_data = query.order_by(
        Transaksi.tanggal.desc()
    ).all()

    total_masuk = sum(
        x.nominal
        for x in all_data
        if x.tipe == "MASUK"
    )

    total_keluar = sum(
        x.nominal
        for x in all_data
        if x.tipe == "KELUAR"
    )

    saldo = total_masuk - total_keluar

    return render_template(
        "index.html",
        data=all_data,
        data_paginated=data_paginated,
        total_masuk=total_masuk,
        total_keluar=total_keluar,
        saldo=saldo,
        start_date="",
        end_date="",
        token=token
    )

# =========================
# LOG REQUEST
# =========================
@app.before_request
def log_all():
    print("=" * 80)
    print("PATH :", request.path)
    print("METHOD :", request.method)
    print("CONTENT TYPE :", request.content_type)
    print("=" * 80)

@app.route("/")
def home():
    return """
    <h2>Finance Assistant</h2>

    Silakan buka dashboard melalui link WhatsApp.
    """
# @app.route("/")
# def index():

#     page = request.args.get("page", 1, type=int)
#     per_page = 10

#     start_date = request.args.get("start_date", "")
#     end_date = request.args.get("end_date", "")

#     query = Transaksi.query

#     if start_date:
#         query = query.filter(
#             db.func.date(Transaksi.tanggal) >= start_date
#         )

#     if end_date:
#         query = query.filter(
#             db.func.date(Transaksi.tanggal) <= end_date
#         )

#     data_paginated = query.order_by(
#         Transaksi.tanggal.desc()
#     ).paginate(
#         page=page,
#         per_page=per_page,
#         error_out=False
#     )

#     all_data = query.order_by(
#         Transaksi.tanggal.desc()
#     ).all()

#     total_masuk = sum(
#         x.nominal for x in all_data
#         if x.tipe == "MASUK"
#     )

#     total_keluar = sum(
#         x.nominal for x in all_data
#         if x.tipe == "KELUAR"
#     )

#     saldo = total_masuk - total_keluar

#     return render_template(
#         "index.html",
#         data=all_data,
#         data_paginated=data_paginated,
#         total_masuk=total_masuk,
#         total_keluar=total_keluar,
#         saldo=saldo,
#         start_date=start_date,
#         end_date=end_date
#     )

# =========================
# EXPORT EXCEL
# =========================
@app.route("/export-excel")
def export_excel():

    # =========================
    # VERIFIKASI TOKEN
    # =========================
    token = request.args.get("token")

    nomor = verify_token(token)

    if not nomor:
        return "Unauthorized", 403

    # =========================
    # FILTER TANGGAL
    # =========================
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    query = Transaksi.query.filter(
        Transaksi.nomor_wa == nomor
    )

    if start_date:
        query = query.filter(
            db.func.date(Transaksi.tanggal) >= start_date
        )

    if end_date:
        query = query.filter(
            db.func.date(Transaksi.tanggal) <= end_date
        )

    # =========================
    # AMBIL DATA
    # =========================
    data = query.order_by(
        Transaksi.tanggal.desc()
    ).all()

    rows = []

    for row in data:

        rows.append({
            "Tanggal": row.tanggal.strftime("%d-%m-%Y %H:%M"),
            "Tipe": row.tipe,
            "Nominal": row.nominal,
            "Keterangan": row.keterangan,
            "Nomor WA": row.nomor_wa
        })

    df = pd.DataFrame(rows)

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Kas WhatsApp"
        )

        worksheet = writer.sheets["Kas WhatsApp"]

        for column in worksheet.columns:

            max_length = 0

            column_letter = column[0].column_letter

            for cell in column:

                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass

            worksheet.column_dimensions[
                column_letter
            ].width = max_length + 3

    output.seek(0)

    filename = (
        f"Kas_WhatsApp_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# =========================
# FONNTE SEND MESSAGE
# =========================
FONTE_TOKEN = os.getenv("FONTE_TOKEN")

def kirim_wa(nomor, pesan):
    try:

        response = requests.post(
            "https://api.fonnte.com/send",
            headers={
                "Authorization": FONTE_TOKEN
            },
            data={
                "target": nomor,
                "message": pesan,
                "delay": 2
            },
            timeout=30
        )

        print("=" * 60)
        print("FONNTE SEND")
        print("TO     :", nomor)
        print("STATUS :", response.status_code)
        print("BODY   :", response.text)
        print("=" * 60)

    except Exception as e:
        print("ERROR FONNTE :", str(e))

def transaksi_user(sender):
    return Transaksi.query.filter(
        Transaksi.nomor_wa == sender
    )

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    payload = request.get_json(silent=True) or {}

    print("=" * 80)
    print("WEBHOOK INCOMING")
    print(payload)
    print("=" * 80)

    # =========================
    # IGNORE STATUS / DELIVERY EVENTS
    # =========================
    if payload.get("status") or payload.get("state"):
        return jsonify({"status": True})

    if payload.get("event") in ["sent", "delivered", "read"]:
        return jsonify({"status": True})

    # =========================
    # EXTRACT DATA (SAFE)
    # =========================
    sender = str(payload.get("sender") or payload.get("from") or "").strip()
    message = str(payload.get("message") or payload.get("text") or "").strip()

    msg_id = payload.get("id") or payload.get("inboxid")

    if not sender or not message:
        return jsonify({"status": True})

    # =========================
    # ANTI LOOP INTELLIGENT FILTER
    # =========================
    lower_msg = message.lower()

    # 1. Ignore pesan dari bot sendiri
    if sender == os.getenv("BOT_NUMBER", ""):
        return jsonify({"status": True})

    # 2. Ignore footer Fonnte
    if "sent via fonnte" in lower_msg:
        return jsonify({"status": True})

    # 3. Ignore balasan bot
    if (
        lower_msg.startswith("[bot]")
        or lower_msg.startswith("📌")
        or lower_msg.startswith("✅")
    ):
        return jsonify({"status": True})

    # =========================
    # SAFE MSG ID
    # =========================
    if not msg_id:
        msg_id = f"{sender}:{int(time.time())}"

    # =========================
    # DUPLICATE FILTER
    # =========================
    if is_duplicate(msg_id):
        return jsonify({"status": True})

    cmd = lower_msg.strip()

    print("SENDER :", sender)
    print("MESSAGE:", message)
    print("CMD    :", cmd)

    # =====================================================
    # HANYA RESPON COMMAND YANG DIKENAL
    # =====================================================
    valid_command = (
        cmd == "saldo"
        or cmd == "hariini"
        or cmd.startswith("masuk")
        or cmd.startswith("keluar")
    )

    if not valid_command:
        print("IGNORE NON COMMAND")
        return jsonify({
            "status": True,
            "ignored": True
        })

    # =========================
    # SALDO
    # =========================
    if cmd == "saldo":

        masuk = transaksi_user(sender).filter(
            Transaksi.tipe == "MASUK"
        ).with_entities(
            db.func.sum(Transaksi.nominal)
        ).scalar() or 0

        keluar = transaksi_user(sender).filter(
            Transaksi.tipe == "KELUAR"
        ).with_entities(
            db.func.sum(Transaksi.nominal)
        ).scalar() or 0

        saldo = masuk - keluar

        link = generate_dashboard_link(sender)

        kirim_wa(
            sender,
            f"""💰 *Saldo Keuangan*

        ━━━━━━━━━━━━━━━━━━

        📥 *Pemasukan*
        Rp {masuk:,.0f}

        📤 *Pengeluaran*
        Rp {keluar:,.0f}

        ━━━━━━━━━━━━━━━━━━

        💳 *Saldo Saat Ini*

        *Rp {saldo:,.0f}*

        📊 *Dashboard*
        {link}
        🔒 Link berlaku 24 jam.
        """
        )

        return jsonify({"status": True})

    # =========================
    # MASUK
    # =========================
    if cmd.startswith("masuk"):

        try:

            parts = message.split()

            nominal = int(parts[1])

            keterangan = (
                " ".join(parts[2:])
                if len(parts) > 2
                else "-"
            )

            link = generate_dashboard_link(sender)

            trx = Transaksi(
                tanggal=sekarang(),
                tipe="MASUK",
                nominal=nominal,
                keterangan=keterangan,
                nomor_wa=sender
            )

            db.session.add(trx)
            db.session.commit()

            kirim_wa(
                sender,
                f"""✅ *Pemasukan Berhasil*

            💵 Nominal
            *Rp {nominal:,.0f}*

            📝 Keterangan
            {keterangan}

            📅 {sekarang().strftime("%d %B %Y")}
            🕒 {sekarang().strftime("%H:%M")}

            📊 *Dashboard*
            {link}
            🔒 Link berlaku 24 jam.
            """
            )

        except Exception:

            kirim_wa(
                sender,
                "Format:\nmasuk 100000 gaji"
            )

        return jsonify({"status": True})

    # =========================
    # KELUAR
    # =========================
    if cmd.startswith("keluar"):

        try:

            parts = message.split()

            nominal = int(parts[1])

            keterangan = (
                " ".join(parts[2:])
                if len(parts) > 2
                else "-"
            )
            link = generate_dashboard_link(sender)
            trx = Transaksi(
                tanggal=sekarang(),
                tipe="KELUAR",
                nominal=nominal,
                keterangan=keterangan,
                nomor_wa=sender
            )

            db.session.add(trx)
            db.session.commit()

            kirim_wa(
                sender,
                f"""💸 *Pengeluaran Berhasil*

            💰 Nominal
            *Rp {nominal:,.0f}*

            📝 Keterangan
            {keterangan}

            📅 {sekarang().strftime("%d %B %Y")}
            🕒 {sekarang().strftime("%H:%M")}

            📊 *Dashboard*
            {link}
            🔒 Link berlaku 24 jam.
            """
            )

        except Exception:

            kirim_wa(
                sender,
                "Format:\nkeluar 25000 makan"
            )

        return jsonify({"status": True})

    # =========================
    # HARI INI
    # =========================
    if cmd == "hariini":

        today = sekarang().date()

        data = transaksi_user(sender).filter(
            db.func.date(Transaksi.tanggal) == today
        ).all()

        total = sum(x.nominal for x in data)
        link = generate_dashboard_link(sender)
        kirim_wa(
            sender,
            f"""📊 *Ringkasan Hari Ini*

        Jumlah Transaksi
        *{len(data)}*

        Total Nominal
        *Rp {total:,.0f}*

        📊 *Dashboard*
            {link}
            🔒 Link berlaku 24 jam.
        """
        )

        return jsonify({"status": True})

    # =========================
    # DEFAULT
    # =========================
    return jsonify({
        "status": True
    })

# =========================
# TEST
# =========================
@app.route("/test-wa")
def test_wa():
    kirim_wa("6285871264448", "Test dari Railway berhasil")
    return {"status": True}


@app.route("/debug-token")
def debug_token():
    token = os.getenv("FONTE_TOKEN")
    return {
        "exists": bool(token),
        "length": len(token) if token else 0
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
