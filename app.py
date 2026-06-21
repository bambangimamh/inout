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
database_url = os.getenv("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    db.create_all()

# =========================
# ENV CONFIG
# =========================
FONTE_TOKEN = os.getenv("FONTE_TOKEN")
BOT_NUMBER = os.getenv("BOT_NUMBER", "")  # nomor WA bot sendiri (opsional)

# =========================
# ANTI DUPLICATE MEMORY
# =========================
PROCESSED = {}

def is_duplicate(msg_id):
    now = time.time()

    # cleanup cache lama (10 menit)
    expired = [k for k, v in PROCESSED.items() if now - v > 600]
    for k in expired:
        del PROCESSED[k]

    if not msg_id:
        return False

    if msg_id in PROCESSED:
        return True

    PROCESSED[msg_id] = now
    return False


# =========================
# FONNTE SENDER
# =========================
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

        print("FONNTE STATUS:", response.status_code)
        print("FONNTE BODY:", response.text)

    except Exception as e:
        print("FONNTE ERROR:", str(e))


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
    # IGNORE STATUS / DELIVERY EVENT
    # =========================
    if payload.get("status") or payload.get("state") or payload.get("event") in [
        "sent", "delivered", "read"
    ]:
        return jsonify({"status": True})

    # =========================
    # EXTRACT DATA
    # =========================
    sender = str(payload.get("sender") or payload.get("from") or "").strip()
    message = str(payload.get("message") or payload.get("text") or "").strip()

    msg_id = payload.get("id") or payload.get("inboxid")

    # fallback safe ID (jangan pakai message saja)
    if not msg_id:
        msg_id = f"{sender}-{message}-{int(time.time())}"

    print("SENDER:", sender)
    print("MESSAGE:", message)
    print("MSG_ID:", msg_id)

    # =========================
    # VALIDATION
    # =========================
    if not sender or not message:
        return jsonify({"status": True})

    # =========================
    # ANTI BOT LOOP (SELF MESSAGE)
    # =========================
    if BOT_NUMBER and sender == BOT_NUMBER:
        return jsonify({"status": True})

    # =========================
    # ANTI DUPLICATE
    # =========================
    if is_duplicate(msg_id):
        print("DUPLICATE IGNORED")
        return jsonify({"status": True})

    # =========================
    # ANTI ECHO FROM FONNTE
    # =========================
    lower_msg = message.lower()

    if "sent via fonnte" in lower_msg:
        return jsonify({"status": True})

    if message.startswith("[BOT]"):
        return jsonify({"status": True})

    cmd = lower_msg.strip()

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
            f"💰 SALDO\n\nMasuk: Rp {masuk:,.0f}\nKeluar: Rp {keluar:,.0f}\nSaldo: Rp {saldo:,.0f}"
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
            print("ERROR MASUK:", str(e))
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

        except Exception as e:
            print("ERROR KELUAR:", str(e))
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
            f"📅 HARI INI\nTransaksi: {len(data)}\nTotal: Rp {total:,.0f}"
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
# TEST ENDPOINT
# =========================
@app.route("/test-wa")
def test_wa():
    kirim_wa("628xxxxxxx", "[BOT] test sukses")
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
