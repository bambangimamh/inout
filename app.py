from flask import Flask
from flask import request
from flask import jsonify
from flask import render_template

from flask_sqlalchemy import SQLAlchemy

from datetime import datetime

from models import db
from models import Transaksi
import requests
import os

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///kas.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


# ==================================
# DASHBOARD
# ==================================
@app.route("/")
def index():

    data = Transaksi.query.order_by(
        Transaksi.tanggal.desc()
    ).all()

    total_masuk = sum(
        x.nominal for x in data
        if x.tipe == "MASUK"
    )

    total_keluar = sum(
        x.nominal for x in data
        if x.tipe == "KELUAR"
    )

    saldo = total_masuk - total_keluar

    return render_template(
        "index.html",
        data=data,
        saldo=saldo,
        total_masuk=total_masuk,
        total_keluar=total_keluar
    )

# @app.route("/")
# def index():
#     return "Railway OK"

FONTE_TOKEN = os.getenv("FONTE_TOKEN")

def kirim_wa(nomor, pesan):

    if not FONTE_TOKEN:
        print("FONTE_TOKEN tidak ditemukan")
        return

    try:

        response = requests.post(
            "https://api.fonnte.com/send",
            headers={
                "Authorization": FONTE_TOKEN
            },
            data={
                "target": nomor,
                "message": pesan
            },
            timeout=20
        )

        print("================================")
        print("KIRIM WA")
        print("Nomor :", nomor)
        print("Status :", response.status_code)
        print("Response :", response.text)
        print("================================")

    except Exception as e:

        print("ERROR KIRIM WA :", str(e))
# ==================================
# WEBHOOK FONTE
# ==================================
# @app.route("/webhook", methods=["POST"])
# def webhook():

#     payload = request.json or {}

#     print("================================")
#     print("WEBHOOK MASUK")
#     print(payload)
#     print("================================")

#     sender = ""
#     message = ""

#     # Format webhook Fonte versi 1
#     if "sender" in payload:
#         sender = payload.get("sender", "")
#         message = payload.get("message", "")

#     # Format webhook Fonte versi 2
#     elif "data" in payload:

#         data = payload.get("data", {})

#         sender = data.get("sender", "")
#         message = data.get("message", "")

#     sender = str(sender).strip()
#     message = str(message).strip()

#     print("SENDER :", sender)
#     print("MESSAGE :", message)

#     if not sender:

#         return jsonify({
#             "status": False,
#             "message": "sender kosong"
#         })

#     if not message:

#         return jsonify({
#             "status": False,
#             "message": "message kosong"
#         })

#     cmd = message.lower()

#     # =========================
#     # KELUAR
#     # =========================

#     if cmd.startswith("keluar"):

#         try:

#             parts = message.split()

#             nominal = int(parts[1])

#             keterangan = " ".join(parts[2:])

#             trx = Transaksi(
#                 tanggal=datetime.now(),
#                 tipe="KELUAR",
#                 nominal=nominal,
#                 keterangan=keterangan,
#                 nomor_wa=sender
#             )

#             db.session.add(trx)
#             db.session.commit()

#             kirim_wa(
#                 sender,
#                 f"✅ Pengeluaran Tersimpan\n\n"
#                 f"Nominal : Rp {nominal:,.0f}\n"
#                 f"Keterangan : {keterangan}"
#             )

#         except Exception as e:

#             print(e)

#             kirim_wa(
#                 sender,
#                 "Format salah.\n\n"
#                 "Contoh:\n"
#                 "keluar 25000 makan siang"
#             )

#         return jsonify({"status": True})

#     # =========================
#     # MASUK
#     # =========================

#     elif cmd.startswith("masuk"):

#         try:

#             parts = message.split()

#             nominal = int(parts[1])

#             keterangan = " ".join(parts[2:])

#             trx = Transaksi(
#                 tanggal=datetime.now(),
#                 tipe="MASUK",
#                 nominal=nominal,
#                 keterangan=keterangan,
#                 nomor_wa=sender
#             )

#             db.session.add(trx)
#             db.session.commit()

#             kirim_wa(
#                 sender,
#                 f"✅ Pemasukan Tersimpan\n\n"
#                 f"Nominal : Rp {nominal:,.0f}\n"
#                 f"Keterangan : {keterangan}"
#             )

#         except Exception as e:

#             print(e)

#             kirim_wa(
#                 sender,
#                 "Format salah.\n\n"
#                 "Contoh:\n"
#                 "masuk 1000000 gaji"
#             )

#         return jsonify({"status": True})

#     # =========================
#     # SALDO
#     # =========================

#     elif cmd == "saldo":

#         masuk = db.session.query(
#             db.func.sum(
#                 Transaksi.nominal
#             )
#         ).filter(
#             Transaksi.tipe == "MASUK"
#         ).scalar() or 0

#         keluar = db.session.query(
#             db.func.sum(
#                 Transaksi.nominal
#             )
#         ).filter(
#             Transaksi.tipe == "KELUAR"
#         ).scalar() or 0

#         saldo = masuk - keluar

#         kirim_wa(
#             sender,
#             f"💰 SALDO SAAT INI\n\n"
#             f"Masuk : Rp {masuk:,.0f}\n"
#             f"Keluar : Rp {keluar:,.0f}\n"
#             f"Saldo : Rp {saldo:,.0f}"
#         )

#         return jsonify({"status": True})

#     # =========================
#     # HARI INI
#     # =========================

#     elif cmd == "hariini":

#         today = datetime.now().date()

#         data = Transaksi.query.filter(
#             db.func.date(
#                 Transaksi.tanggal
#             ) == today
#         ).all()

#         total = sum(
#             x.nominal for x in data
#         )

#         kirim_wa(
#             sender,
#             f"📅 TRANSAKSI HARI INI\n\n"
#             f"Jumlah : {len(data)}\n"
#             f"Total : Rp {total:,.0f}"
#         )

#         return jsonify({"status": True})

#     # =========================
#     # HELP
#     # =========================

#     kirim_wa(
#         sender,
#         "📌 Perintah Yang Tersedia\n\n"
#         "masuk 100000 gaji\n"
#         "keluar 25000 makan\n"
#         "saldo\n"
#         "hariini"
#     )

#     return jsonify({
#         "status": True
#     })

@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    print("\n")
    print("=" * 60)
    print("WEBHOOK MASUK")
    print("METHOD :", request.method)

    print("FORM :", request.form.to_dict())

    print("JSON :", request.get_json(silent=True))

    print("ARGS :", request.args.to_dict())

    print("=" * 60)

    return jsonify({
        "status": True
    })

@app.route("/test-wa")
def test_wa():

    response = requests.post(
        "https://api.fonnte.com/send",
        headers={
            "Authorization": FONTE_TOKEN
        },
        data={
            "target": "6285872362212",
            "message": "Test dari Railway"
        }
    )

    return {
        "status_code": response.status_code,
        "response": response.text
    }

@app.route("/debug-token")
def debug_token():

    token = os.getenv("FONTE_TOKEN")

    return {
        "exists": bool(token),
        "length": len(token) if token else 0
    }

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
