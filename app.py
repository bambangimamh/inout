from flask import Flask
from flask import request
from flask import jsonify
from flask import render_template

from flask_sqlalchemy import SQLAlchemy

from datetime import datetime

from models import db
from models import Transaksi

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///kas.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


# ==================================
# DASHBOARD
# ==================================
# @app.route("/")
# def index():

#     data = Transaksi.query.order_by(
#         Transaksi.tanggal.desc()
#     ).all()

#     total_masuk = sum(
#         x.nominal for x in data
#         if x.tipe == "MASUK"
#     )

#     total_keluar = sum(
#         x.nominal for x in data
#         if x.tipe == "KELUAR"
#     )

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
    return "Railway OK"


# ==================================
# WEBHOOK FONTE
# ==================================
@app.route("/webhook", methods=["POST"])
def webhook():

    payload = request.json

    sender = payload.get("sender", "")

    message = payload.get("message", "").strip()

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

            return jsonify({
                "reply":
                f"✅ Pengeluaran tersimpan\n\n"
                f"Rp {nominal:,.0f}\n"
                f"{keterangan}"
            })

        except:

            return jsonify({
                "reply":
                "Format:\nkeluar 25000 makan siang"
            })

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

            return jsonify({
                "reply":
                f"✅ Pemasukan tersimpan\n\n"
                f"Rp {nominal:,.0f}\n"
                f"{keterangan}"
            })

        except:

            return jsonify({
                "reply":
                "Format:\nmasuk 1000000 gaji"
            })

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

        return jsonify({
            "reply":
            f"💰 Saldo Saat Ini\n\n"
            f"Masuk : Rp {masuk:,.0f}\n"
            f"Keluar : Rp {keluar:,.0f}\n"
            f"Saldo : Rp {saldo:,.0f}"
        })

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

        total = sum(x.nominal for x in data)

        return jsonify({
            "reply":
            f"📅 Hari Ini\n"
            f"Jumlah Transaksi : {len(data)}\n"
            f"Total : Rp {total:,.0f}"
        })

    return jsonify({
        "reply":
        "Perintah:\n\n"
        "masuk 100000 gaji\n"
        "keluar 25000 makan\n"
        "saldo\n"
        "hariini"
    })


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
