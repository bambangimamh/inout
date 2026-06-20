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

    try:

        requests.post(
            "https://api.fonnte.com/send",
            headers={
                "Authorization": FONTE_TOKEN
            },
            data={
                "target": nomor,
                "message": pesan
            },
            timeout=10
        )

    except Exception as e:

        print("ERROR KIRIM WA:", e)

# ==================================
# WEBHOOK FONTE
# ==================================
@app.route("/webhook", methods=["POST"])
def webhook():

    payload = request.json or {}

    print("PAYLOAD FONTE:")
    print(payload)

    sender = payload.get("sender", "")
    message = payload.get("message", "")

    if not sender or not message:
        return jsonify({
            "status": False
        })

    message = str(message).strip()

    cmd = message.lower()

    # =========================
    # KELUAR
    # =========================

    if cmd.startswith("keluar"):

        try:

            parts = message.split()

            nominal = int(parts[1])

            keterangan = " ".join(parts[2:])

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
                f"✅ Pengeluaran Tersimpan\n\n"
                f"Nominal : Rp {nominal:,.0f}\n"
                f"Keterangan : {keterangan}"
            )

        except Exception as e:

            print(e)

            kirim_wa(
                sender,
                "Format salah.\n\n"
                "Contoh:\n"
                "keluar 25000 makan siang"
            )

        return jsonify({"status": True})

    # =========================
    # MASUK
    # =========================

    elif cmd.startswith("masuk"):

        try:

            parts = message.split()

            nominal = int(parts[1])

            keterangan = " ".join(parts[2:])

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
                f"✅ Pemasukan Tersimpan\n\n"
                f"Nominal : Rp {nominal:,.0f}\n"
                f"Keterangan : {keterangan}"
            )

        except Exception as e:

            print(e)

            kirim_wa(
                sender,
                "Format salah.\n\n"
                "Contoh:\n"
                "masuk 1000000 gaji"
            )

        return jsonify({"status": True})

    # =========================
    # SALDO
    # =========================

    elif cmd == "saldo":

        masuk = db.session.query(
            db.func.sum(
                Transaksi.nominal
            )
        ).filter(
            Transaksi.tipe == "MASUK"
        ).scalar() or 0

        keluar = db.session.query(
            db.func.sum(
                Transaksi.nominal
            )
        ).filter(
            Transaksi.tipe == "KELUAR"
        ).scalar() or 0

        saldo = masuk - keluar

        kirim_wa(
            sender,
            f"💰 SALDO SAAT INI\n\n"
            f"Masuk : Rp {masuk:,.0f}\n"
            f"Keluar : Rp {keluar:,.0f}\n"
            f"Saldo : Rp {saldo:,.0f}"
        )

        return jsonify({"status": True})

    # =========================
    # HARI INI
    # =========================

    elif cmd == "hariini":

        today = datetime.now().date()

        data = Transaksi.query.filter(
            db.func.date(
                Transaksi.tanggal
            ) == today
        ).all()

        total = sum(
            x.nominal for x in data
        )

        kirim_wa(
            sender,
            f"📅 TRANSAKSI HARI INI\n\n"
            f"Jumlah : {len(data)}\n"
            f"Total : Rp {total:,.0f}"
        )

        return jsonify({"status": True})

    # =========================
    # HELP
    # =========================

    kirim_wa(
        sender,
        "📌 Perintah Yang Tersedia\n\n"
        "masuk 100000 gaji\n"
        "keluar 25000 makan\n"
        "saldo\n"
        "hariini"
    )

    return jsonify({
        "status": True
    })


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
