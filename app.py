from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from models import db, Transaksi
import requests
import os
import time

app = Flask(__name__)

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


# =========================
# DASHBOARD
# =========================
# @app.route("/")
# def index():
#     data = Transaksi.query.order_by(Transaksi.tanggal.desc()).all()

#     total_masuk = sum(x.nominal for x in data if x.tipe == "MASUK")
#     total_keluar = sum(x.nominal for x in data if x.tipe == "KELUAR")
#     saldo = total_masuk - total_keluar

#     return render_template(
#         "index.html",
#         data=data,
#         saldo=saldo,
#         total_masuk=total_masuk,
#         total_keluar=total_keluar
#     )

@app.route("/")
def index():

    page = request.args.get("page", 1, type=int)
    per_page = 10

    data_paginated = Transaksi.query.order_by(
        Transaksi.tanggal.desc()
    ).paginate(page=page, per_page=per_page)

    all_data = Transaksi.query.all()

    total_masuk = sum(x.nominal for x in all_data if x.tipe == "MASUK")
    total_keluar = sum(x.nominal for x in all_data if x.tipe == "KELUAR")
    saldo = total_masuk - total_keluar

    return render_template(
        "index.html",
        data=all_data,
        data_paginated=data_paginated,
        total_masuk=total_masuk,
        total_keluar=total_keluar,
        saldo=saldo
    )

# =========================
# FONNTE SEND MESSAGE
# =========================
FONTE_TOKEN = os.getenv("FONTE_TOKEN")

def kirim_wa(nomor, pesan):
    try:
        response = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": FONTE_TOKEN},
            data={
                "target": nomor,
                "message": pesan
            },
            timeout=30
        )

        print("========== FONNTE ==========")
        print("STATUS :", response.status_code)
        print("BODY :", response.text)
        print("============================")

    except Exception as e:
        print("ERROR FONNTE :", str(e))


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

    # 1. IGNORE MESSAGE FROM BOT SYSTEM ITSELF
    if sender == os.getenv("BOT_NUMBER", ""):
        return jsonify({"status": True})

    # 2. IGNORE FONNTE SYSTEM MESSAGE
    if "sent via fonnte" in lower_msg:
        return jsonify({"status": True})

    # 3. IGNORE BOT RESPONSE (CRITICAL LOOP STOP)
    if lower_msg.startswith("[bot]") or lower_msg.startswith("📌") or lower_msg.startswith("✅"):
        return jsonify({"status": True})

    # =========================
    # SAFE MSG ID (NO FALLBACK TO MESSAGE)
    # =========================
    if not msg_id:
        msg_id = f"{sender}:{int(time.time())}"

    # =========================
    # OPTIONAL DEDUP (LIGHT)
    # =========================
    if is_duplicate(msg_id):
        return jsonify({"status": True})

    cmd = lower_msg.strip()

    print("SENDER:", sender)
    print("MESSAGE:", message)
    print("CMD:", cmd)

    # =========================
    # SALDO
    # =========================
    if cmd == "saldo":

        masuk = db.session.query(db.func.sum(Transaksi.nominal))\
            .filter(Transaksi.tipe == "MASUK").scalar() or 0

        keluar = db.session.query(db.func.sum(Transaksi.nominal))\
            .filter(Transaksi.tipe == "KELUAR").scalar() or 0

        saldo = masuk - keluar

        kirim_wa(
            sender,
            f"[BOT] 💰 SALDO\nMasuk: Rp {masuk:,.0f}\nKeluar: Rp {keluar:,.0f}\nSaldo: Rp {saldo:,.0f}"
        )

        return jsonify({"status": True})

    # =========================
    # MASUK
    # =========================
    if cmd.startswith("masuk"):

        try:
            parts = message.split()
            nominal = int(parts[1])
            keterangan = " ".join(parts[2:]) if len(parts) > 2 else "-"

            trx = Transaksi(
                tanggal=datetime.now(),
                tipe="MASUK",
                nominal=nominal,
                keterangan=keterangan,
                nomor_wa=sender
            )

            db.session.add(trx)
            db.session.commit()

            kirim_wa(
                sender,
                f"[BOT] ✅ MASUK tersimpan\nRp {nominal:,.0f}\n{keterangan}"
            )

        except Exception as e:
            kirim_wa(sender, "Format: masuk 100000 gaji")

        return jsonify({"status": True})

    # =========================
    # KELUAR
    # =========================
    if cmd.startswith("keluar"):

        try:
            parts = message.split()
            nominal = int(parts[1])
            keterangan = " ".join(parts[2:]) if len(parts) > 2 else "-"

            trx = Transaksi(
                tanggal=datetime.now(),
                tipe="KELUAR",
                nominal=nominal,
                keterangan=keterangan,
                nomor_wa=sender
            )

            db.session.add(trx)
            db.session.commit()

            kirim_wa(
                sender,
                f"[BOT] ✅ KELUAR tersimpan\nRp {nominal:,.0f}\n{keterangan}"
            )

        except Exception:
            kirim_wa(sender, "Format: keluar 25000 makan")

        return jsonify({"status": True})

    # =========================
    # HARI INI
    # =========================
    if cmd == "hariini":

        today = datetime.now().date()

        data = Transaksi.query.filter(
            db.func.date(Transaksi.tanggal) == today
        ).all()

        total = sum(x.nominal for x in data)

        kirim_wa(
            sender,
            f"[BOT] 📅 HARI INI\nJumlah: {len(data)}\nTotal: Rp {total:,.0f}"
        )

        return jsonify({"status": True})

    # =========================
    # DEFAULT HELP
    # =========================
    kirim_wa(
        sender,
        "📌 MENU:\nmasuk 100000 gaji\nkeluar 25000 makan\nsaldo\nhariini"
    )

    return jsonify({"status": True})

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
