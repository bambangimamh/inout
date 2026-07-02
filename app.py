from flask import Flask, request, jsonify, render_template, send_file, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from models import db, Transaksi, Budget, Reminder, User
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

KATEGORI = {

    "makanan": [
        "bakso",
        "mie",
        "ayam",
        "geprek",
        "pizza",
        "burger",
        "kebab",
        "martabak",
        "sate",
        "nasi",
        "warteg",
        "padang",
        "seafood",
        "pempek",
        "siomay",
        "batagor",
        "snack",
        "cemilan"
    ],

    "minuman": [
        "kopi",
        "es kopi",
        "teh",
        "es teh",
        "jus",
        "boba",
        "chatime",
        "starbucks",
        "janji jiwa",
        "kopi kenangan",
        "air",
        "galon",
        "susu"
    ],

    "transport": [
        "grab",
        "gojek",
        "maxim",
        "gocar",
        "goride",
        "bensin",
        "pertalite",
        "pertamax",
        "solar",
        "parkir",
        "tol",
        "kereta",
        "bus"
    ],

    "belanja": [
        "indomaret",
        "alfamart",
        "superindo",
        "hypermart",
        "sayur",
        "buah",
        "beras",
        "telur",
        "daging",
        "sembako"
    ],

    "tagihan": [
        "pln",
        "listrik",
        "air",
        "pam",
        "wifi",
        "internet",
        "indihome",
        "biznet",
        "pulsa",
        "bpjs"
    ],

    "hiburan": [
        "netflix",
        "spotify",
        "bioskop",
        "xxi",
        "cgv",
        "steam",
        "game",
        "playstation"
    ],

    "kesehatan": [
        "dokter",
        "obat",
        "apotek",
        "vitamin",
        "rumah sakit",
        "lab"
    ],

    "pendidikan": [
        "sekolah",
        "kampus",
        "buku",
        "kursus",
        "sertifikasi"
    ],

    "investasi": [
        "saham",
        "reksadana",
        "emas",
        "crypto",
        "bitcoin",
        "obligasi"
    ]
}

def cari_kategori(keterangan):

    teks = keterangan.lower()

    for kategori, daftar in KATEGORI.items():

        for sub in daftar:

            if sub in teks:

                return kategori, sub

    return "lainnya", "lainnya"

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

@app.route("/admin/users")
def admin_users():

    search = request.args.get("search","")

    page = request.args.get(
        "page",
        1,
        type=int
    )

    query = User.query

    if search:

        query = query.filter(
            User.nomor_wa.contains(search)
        )

    users = query.order_by(
        User.created_at.desc()
    ).paginate(
        page=page,
        per_page=15
    )

    return render_template(
        "admin_users.html",
        users=users,
        search=search
    )

@app.route("/admin/users/add",methods=["POST"])
def add_user():

    nama=request.form["nama"]

    nomor=request.form["nomor"]

    if User.query.filter_by(
        nomor_wa=nomor
    ).first():

        return redirect("/admin/users")

    db.session.add(

        User(
            nama=nama,
            nomor_wa=nomor
        )

    )

    db.session.commit()

    return redirect("/admin/users")

@app.route("/admin/users/toggle/<int:id>")
def toggle_user(id):

    user=User.query.get_or_404(id)

    user.aktif=not user.aktif

    db.session.commit()

    return redirect("/admin/users")

@app.route("/admin/users/delete/<int:id>")
def delete_user(id):

    user=User.query.get_or_404(id)

    db.session.delete(user)

    db.session.commit()

    return redirect("/admin/users")

@app.route("/dashboard/<token>")
def dashboard(token):

    nomor = verify_token(token)

    if not nomor:
        return "Link sudah tidak berlaku.", 403

    # =========================
    # PARAMETER
    # =========================

    page = request.args.get("page", 1, type=int)
    per_page = 10

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    # =========================
    # QUERY DASAR
    # =========================

    query = Transaksi.query.filter(
        Transaksi.nomor_wa == nomor
    )

    # =========================
    # FILTER TANGGAL
    # =========================

    try:
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(
                Transaksi.tanggal >= start
            )

        if end_date:
            # +1 hari agar seluruh transaksi pada tanggal tersebut ikut terambil
            end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(
                Transaksi.tanggal < end
            )

    except ValueError:
        # Abaikan jika format tanggal tidak valid
        pass

    # =========================
    # PAGINATION
    # =========================

    data_paginated = query.order_by(
        Transaksi.tanggal.desc()
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    # =========================
    # DATA UNTUK CHART & SUMMARY
    # =========================

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

    # =========================
    # RENDER
    # =========================

    return render_template(
        "index.html",
        data=all_data,
        data_paginated=data_paginated,
        total_masuk=total_masuk,
        total_keluar=total_keluar,
        saldo=saldo,
        start_date=start_date,
        end_date=end_date,
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
    return render_template("home.html")

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
# VALIDASI USER
# =========================
def user_terdaftar(nomor):

    nomor = normalize_wa(nomor)

    return User.query.filter(
        User.nomor_wa == nomor,
        User.aktif.is_(True)
    ).first()

# =========================
# VALIDASI FORMAT PENOMORAN
# =========================
def normalize_wa(nomor):

    nomor = str(nomor).strip()

    nomor = nomor.replace("@s.whatsapp.net", "")
    nomor = nomor.replace("+", "")
    nomor = nomor.replace(" ", "")
    nomor = nomor.replace("-", "")

    if nomor.startswith("08"):
        nomor = "62" + nomor[1:]

    return nomor

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

    # ======================================
    # IGNORE STATUS EVENT
    # ======================================

    if payload.get("status") or payload.get("state"):
        return jsonify(status=True)

    if payload.get("event") in [
        "sent",
        "delivered",
        "read"
    ]:
        return jsonify(status=True)

    # ======================================
    # AMBIL DATA
    # ======================================

    sender = normalize_wa(
        payload.get("sender")
        or payload.get("pengirim")
        or payload.get("from")
        or ""
    )

    message = str(
        payload.get("message")
        or payload.get("pesan")
        or ""
    ).strip()

    msg_id = (
        payload.get("id")
        or payload.get("inboxid")
        or f"{sender}:{int(time.time())}"
    )

    if not sender:
        return jsonify(status=True)

    if not message:
        return jsonify(status=True)

    lower_msg = message.lower()

    print("Sender :", sender)
    print("Message:", message)

    # ======================================
    # ANTI LOOP
    # ======================================

    # pesan dari bot sendiri
    if message.startswith("[BOT]"):
        return jsonify(status=True)

    # footer fonnte
    if "sent via fonnte" in lower_msg:
        return jsonify(status=True)

    # balasan bot
    if "chatsaku finance assistant" in lower_msg:
        return jsonify(status=True)

    if "nomor belum terdaftar" in lower_msg:
        return jsonify(status=True)

    # nomor bot sendiri
    bot_number = normalize_wa(
        os.getenv("BOT_NUMBER", "")
    )

    if sender == bot_number:
        return jsonify(status=True)

    # ======================================
    # DUPLICATE FILTER
    # ======================================

    if is_duplicate(msg_id):
        return jsonify(status=True)

    # ======================================
    # VALIDASI USER
    # ======================================

    user = user_terdaftar(sender)

    print("User :", user)

    if not user:

        print("UNREGISTERED :", sender)

        kirim_wa(
            sender,
            """🚫 *Nomor Belum Terdaftar*

Maaf, nomor WhatsApp Anda belum terdaftar pada sistem *ChatSaku Finance*.

Silakan hubungi Admin untuk mengaktifkan akun Anda.

https://www.chatsaku.com

💚 ChatSaku Finance Assistant
"""
        )

        return jsonify(
            status=True,
            registered=False
        )

    # ======================================
    # COMMAND
    # ======================================

    cmd = lower_msg.strip()

    print("CMD :", cmd)

    print("SENDER :", sender)
    print("MESSAGE:", message)
    print("CMD    :", cmd)

    # =====================================================
    # HANYA RESPON COMMAND YANG DIKENAL
    # =====================================================
    valid_command = (
        cmd == "saldo"
        or cmd == "hariini"
        or cmd == "insight"
        or cmd.startswith("masuk")
        or cmd.startswith("keluar")
        or cmd.startswith("budget")
        or cmd.startswith("reminder")
        or cmd.startswith("hapusreminder")
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
            f"""💳 *Saldo Keuangan*
┌────────────────┐
📥 Masuk   : Rp {masuk:,.0f}
📤 Keluar  : Rp {keluar:,.0f}
 ─────────────────
💰 Saldo   : *Rp {saldo:,.0f}*
└────────────────┘

📊 Dashboard
{link}

🕒 Berlaku 24 jam

🤖 ChatSaku Finance Assistant
💚 Kelola keuangan langsung dari WhatsApp
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

            kirim_wa(
                sender,
                f"""✅ *Transaksi Berhasil*
┌────────────────────
💰 *KREDIT MASUK*

💵 Nominal
Rp {nominal:,.0f}

📝 Keterangan
{keterangan}

🕒 {sekarang().strftime("%d %b %Y • %H:%M")}
└────────────────────

💳 *Saldo Saat Ini*
Rp {saldo:,.0f}

📊 Dashboard
{link}

⏳ Link aktif 24 jam

━━━━━━━━━━━━━━━━━━
🤖 ChatSaku Finance Assistant
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

            if len(parts) < 3:

                kirim_wa(
                    sender,
                    "Format:\nkeluar 25000 grab"
                )

                return jsonify({"status": True})

            nominal = int(
                parts[1]
                .replace(".", "")
                .replace(",", "")
            )

            keterangan = " ".join(parts[2:])

            kategori, subkategori = cari_kategori(keterangan)

            trx = Transaksi(
                tanggal=sekarang(),
                tipe="KELUAR",
                nominal=nominal,
                kategori=kategori,
                subkategori=subkategori,
                keterangan=keterangan,
                nomor_wa=sender
            )

            db.session.add(trx)
            db.session.commit()

            # ======================================
            # TOTAL SALDO
            # ======================================

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

            # ======================================
            # DASHBOARD
            # ======================================

            link = generate_dashboard_link(sender)

            # ======================================
            # BUDGET
            # ======================================

            periode = periode_sekarang()

            budget = Budget.query.filter_by(
                nomor_wa=sender,
                kategori=kategori,
                periode=periode
            ).first()

            budget_text = ""

            if budget:

                # awal & akhir bulan
                now = sekarang()

                awal_bulan = now.replace(
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0
                )

                if now.month == 12:
                    akhir_bulan = now.replace(
                        year=now.year + 1,
                        month=1,
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0
                    )
                else:
                    akhir_bulan = now.replace(
                        month=now.month + 1,
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0
                    )

                total_keluar = transaksi_user(sender).filter(
                    Transaksi.tipe == "KELUAR",
                    Transaksi.kategori == kategori,
                    Transaksi.tanggal >= awal_bulan,
                    Transaksi.tanggal < akhir_bulan
                ).with_entities(
                    db.func.sum(Transaksi.nominal)
                ).scalar() or 0

                persen = (
                    (total_keluar / budget.nominal) * 100
                    if budget.nominal > 0 else 0
                )

                sisa = budget.nominal - total_keluar

                blok = min(10, int(persen / 10))
                bar = "🟩" * blok + "⬜" * (10 - blok)

                if persen <= 50:
                    status = "🟢 Budget Aman"

                elif persen <= 80:
                    status = "🟡 Perlu Perhatian"

                elif persen <= 100:
                    status = "🟠 Hampir Habis"

                else:
                    status = "🔴 Budget Terlampaui"

                budget_text = f"""
──────────────────
🏦 *Budget Bulan Ini*

🏷️ Kategori
{kategori.title()}

💰 Budget
Rp {budget.nominal:,.0f}

💸 Terpakai
Rp {total_keluar:,.0f}

💳 Sisa Budget
Rp {max(sisa,0):,.0f}

📊 Progress
{persen:.1f}%

{bar}

{status}
"""

                if persen > 100:

                    over = total_keluar - budget.nominal

                    budget_text += f"""

⚠️ Melebihi Budget
Rp {over:,.0f}
"""

            else:

                budget_text = """
 ──────────────────

🏦 *Budget Bulan Ini*

ℹ️ Belum ada budget untuk kategori ini.

Contoh:
budget transport 1000000
"""

            kirim_wa(
                sender,
                f"""🏦 *Notifikasi Transaksi*
──────────────────

✅ *Debit Berhasil*
💸 - Rp {nominal:,.0f}

🏷️ Kategori
{kategori.title()}

📂 Subkategori
{subkategori.title()}

📝 Keterangan
{keterangan}

🕒 {sekarang().strftime("%d %b %Y • %H:%M")}

{budget_text}

──────────────────

💳 Saldo Tersedia
*Rp {saldo:,.0f}*

📈 Dashboard
{link}

⏳ Link aktif 24 jam

──────────────────
🤖 ChatSaku Finance Assistant
"""
            )

        except Exception as e:

            print(e)

            kirim_wa(
                sender,
                f"""❌ Terjadi kesalahan

{e}

Format:
keluar 25000 grab
"""
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
        masuk_hari_ini = sum(
            x.nominal for x in data
            if x.tipe == "MASUK"
        )

        keluar_hari_ini = sum(
            x.nominal for x in data
            if x.tipe == "KELUAR"
        )

        kirim_wa(
            sender,
            f"""📊 *Ringkasan Hari Ini*
━━━━━━━━━━━━━━

🧾 *Jumlah Transaksi*
{len(data)}

📥 *Pemasukan*
Rp {masuk_hari_ini:,.0f}

📤 *Pengeluaran*
Rp {keluar_hari_ini:,.0f}

━━━━━━━━━━━━━━

💰 *Total Aktivitas*
Rp {total:,.0f}

📊 *Dashboard*
{link}

🔒 Link berlaku selama *24 jam*.

━━━━━━━━━━━━━━
🤖 *Finance Assistant*
"""
        )

        return jsonify({"status": True})

    # =========================
    # BUDGET
    # =========================
    if cmd.startswith("budget"):

        try:

            parts = message.lower().split()

            # =========================
            # LIHAT BUDGET
            # =========================
            if len(parts) == 1:

                periode = periode_sekarang()

                budgets = Budget.query.filter_by(
                    nomor_wa=sender,
                    periode=periode
                ).order_by(
                    Budget.kategori.asc()
                ).all()

                if not budgets:

                    kirim_wa(
                        sender,
                        "📭 Belum ada budget bulan ini.\n\n"
                        "Contoh:\n"
                        "budget makanan 1500000"
                    )

                    return jsonify({"status": True})

                pesan = f"🎯 *Budget Bulan {periode}*\n"
                pesan += "━━━━━━━━━━━━━━\n\n"

                total_budget = 0
                total_terpakai = 0

                for b in budgets:

                    total_budget += b.nominal

                    now = datetime.now()

                    awal_bulan = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

                    if now.month == 12:
                        akhir_bulan = now.replace(year=now.year + 1, month=1, day=1,
                                                hour=0, minute=0, second=0, microsecond=0)
                    else:
                        akhir_bulan = now.replace(month=now.month + 1, day=1,
                                                hour=0, minute=0, second=0, microsecond=0)

                    # =============================
                    # TOTAL PENGELUARAN KATEGORI BULAN INI
                    # =============================
                    terpakai = transaksi_user(sender).filter(
                        Transaksi.tipe == "KELUAR",
                        Transaksi.kategori == b.kategori,
                        Transaksi.tanggal >= awal_bulan,
                        Transaksi.tanggal < akhir_bulan
                    ).with_entities(
                        db.func.sum(Transaksi.nominal)
                    ).scalar() or 0

                    total_terpakai += terpakai

                    persen = (
                        (terpakai / b.nominal) * 100
                        if b.nominal > 0 else 0
                    )

                    sisa = b.nominal - terpakai

                    blok = min(10, int(persen / 10))

                    progress = (
                        "🟩" * blok +
                        "⬜" * (10 - blok)
                    )

                    if persen < 50:
                        status = "🟢 Aman"

                    elif persen < 80:
                        status = "🟡 Waspada"

                    elif persen <= 100:
                        status = "🟠 Hampir Habis"

                    else:
                        status = "🔴 Terlampaui"

                    pesan += (
                        f"📂 *{b.kategori.title()}*\n"
                        f"💰 Budget   : Rp {b.nominal:,.0f}\n"
                        f"📉 Terpakai : Rp {terpakai:,.0f}\n"
                        f"💵 Sisa     : Rp {max(sisa,0):,.0f}\n"
                        f"📊 {persen:.1f}%\n"
                        f"{progress}\n"
                        f"{status}\n\n"
                    )

                pesan += "━━━━━━━━━━━━━━\n"

                total_persen = (
                    (total_terpakai / total_budget) * 100
                    if total_budget > 0 else 0
                )

                blok = min(10, int(total_persen / 10))

                progress = (
                    "🟩" * blok +
                    "⬜" * (10 - blok)
                )

                pesan += (
                    f"💼 *TOTAL BUDGET*\n\n"
                    f"💰 Budget   : Rp {total_budget:,.0f}\n"
                    f"📉 Terpakai : Rp {total_terpakai:,.0f}\n"
                    f"💵 Sisa     : Rp {max(total_budget-total_terpakai,0):,.0f}\n\n"
                    f"📊 {total_persen:.1f}%\n"
                    f"{progress}"
                )

                kirim_wa(sender, pesan)

                return jsonify({"status": True})

            # =========================
            # FORMAT
            # =========================
            if len(parts) < 3:

                kirim_wa(
                    sender,
                    "Format:\n"
                    "budget makanan 1500000"
                )

                return jsonify({"status":True})

            kategori = parts[1].lower()

            # =========================
            # VALIDASI KATEGORI
            # =========================
            if kategori not in KATEGORI.keys():

                daftar = "\n".join(
                    f"• {x.title()}"
                    for x in KATEGORI.keys()
                )

                kirim_wa(
                    sender,
                    f"""❌ Kategori tidak tersedia.

Kategori:

{daftar}

Contoh:
budget makanan 1500000
"""
                )

                return jsonify({"status":True})

            nominal = int(
                parts[2]
                .replace(".","")
                .replace(",","")
            )

            periode = periode_sekarang()

            budget = Budget.query.filter_by(
                nomor_wa=sender,
                kategori=kategori,
                periode=periode
            ).first()

            if budget:

                budget.nominal = nominal

                status = "Diperbarui"

            else:

                budget = Budget(
                    nomor_wa=sender,
                    kategori=kategori,
                    nominal=nominal,
                    periode=periode
                )

                db.session.add(budget)

                status = "Dibuat"

            db.session.commit()

            kirim_wa(
                sender,
                f"""🎯 *Budget {status}*
━━━━━━━━━━━━━━

📂 Kategori
{kategori.title()}

💰 Budget
Rp {nominal:,.0f}

📅 Periode
{periode}

━━━━━━━━━━━━━━

Ketik *budget*
untuk melihat semua budget.
"""
            )

        except Exception as e:

            print(e)

            kirim_wa(
                sender,
                f"Terjadi kesalahan.\n\n{e}"
            )

        return jsonify({"status":True})

    # =========================
    # AI INSIGHT
    # =========================
    if cmd == "insight":

        try:

            periode = periode_sekarang()

            data = transaksi_user(sender).filter(
                Transaksi.tipe == "KELUAR"
            ).all()

            if not data:

                kirim_wa(
                    sender,
                    "📭 Belum ada transaksi yang dapat dianalisis."
                )

                return jsonify({"status": True})

            # =====================================
            # TOTAL
            # =====================================

            total = sum(x.nominal for x in data)

            # =====================================
            # KATEGORI
            # =====================================

            kategori = {}

            for trx in data:

                key = trx.kategori or "Lainnya"

                kategori[key] = kategori.get(key, 0) + trx.nominal

            kategori_terbesar = max(
                kategori,
                key=kategori.get
            )

            nominal_terbesar = kategori[kategori_terbesar]

            persen = nominal_terbesar / total * 100

            # =====================================
            # BUDGET
            # =====================================

            budget = Budget.query.filter_by(
                nomor_wa=sender,
                kategori=kategori_terbesar,
                periode=periode
            ).first()

            budget_info = ""

            if budget:

                persen_budget = (
                    nominal_terbesar /
                    budget.nominal
                ) * 100

                sisa = budget.nominal - nominal_terbesar

                budget_info = f"""

🎯 Budget {kategori_terbesar.title()}
Rp {budget.nominal:,.0f}

📉 Terpakai
Rp {nominal_terbesar:,.0f}

💵 Sisa
Rp {max(sisa,0):,.0f}

📊 {persen_budget:.1f}%
"""

            # =====================================
            # FINANCE SCORE
            # =====================================

            score = 100

            if persen > 50:
                score -= 20

            elif persen > 35:
                score -= 10

            if budget:

                if persen_budget > 100:
                    score -= 25

                elif persen_budget > 80:
                    score -= 10

            if score >= 90:
                status = "🟢 Sangat Sehat"

            elif score >= 75:
                status = "🟢 Sehat"

            elif score >= 60:
                status = "🟡 Cukup"

            elif score >= 40:
                status = "🟠 Perlu Perhatian"

            else:
                status = "🔴 Boros"

            # =====================================
            # REKOMENDASI
            # =====================================

            rekomendasi = []

            if persen > 50:

                rekomendasi.append(
                    f"• Kurangi pengeluaran {kategori_terbesar.title()}."
                )

            if budget and persen_budget > 100:

                rekomendasi.append(
                    "• Budget kategori sudah terlampaui."
                )

            elif budget and persen_budget > 80:

                rekomendasi.append(
                    "• Budget hampir habis."
                )

            if not rekomendasi:

                rekomendasi.append(
                    "• Pengeluaran masih terkendali."
                )

            kirim_wa(
                sender,
                f"""🏦 *AI Finance Insight*
──────────────────

📊 Analisis Pengeluaran

💸 Total Debit
Rp {total:,.0f}

🏷️ Kategori Terbesar
{kategori_terbesar.title()}

💰 Nominal
Rp {nominal_terbesar:,.0f}

📈 Kontribusi
{persen:.1f}% dari total

{budget_info}

──────────────────

💳 *Finance Score*

✨ {score}/100

{status}

──────────────────

🧠 *Rekomendasi AI*

{chr(10).join(rekomendasi)}

──────────────────

🤖 ChatSaku Finance Assistant
💚 AI Powered • WhatsApp Finance
"""
            )

        except Exception as e:

            print(e)

            kirim_wa(
                sender,
                f"Terjadi kesalahan\n\n{e}"
            )

        return jsonify({"status": True})

    # =========================
    # REMINDER
    # =========================
    if cmd.startswith("reminder"):

        try:

            parts = message.lower().split()

            # =========================
            # LIHAT REMINDER
            # =========================
            if len(parts) == 1:

                reminders = Reminder.query.filter_by(
                    nomor_wa=sender,
                    aktif=True
                ).order_by(
                    Reminder.tanggal.asc()
                ).all()

                if not reminders:

                    kirim_wa(
                        sender,
                        "📭 Belum ada reminder.\n\n"
                        "Contoh:\n"
                        "reminder listrik 20 500000"
                    )

                    return jsonify({"status": True})

                pesan = "🔔 *Reminder Tagihan*\n"
                pesan += "━━━━━━━━━━━━━━\n\n"

                total = 0

                for r in reminders:

                    total += r.nominal

                    pesan += (
                        f"📄 {r.nama.title()}\n"
                        f"📅 Tanggal : {r.tanggal}\n"
                        f"💰 Rp {r.nominal:,.0f}\n\n"
                    )

                pesan += "━━━━━━━━━━━━━━\n"
                pesan += f"💵 Total Tagihan\nRp {total:,.0f}"

                kirim_wa(sender, pesan)

                return jsonify({"status": True})

            # =========================
            # FORMAT
            # =========================
            if len(parts) < 4:

                kirim_wa(
                    sender,
                    "Format:\n"
                    "reminder listrik 20 500000"
                )

                return jsonify({"status": True})

            nama = parts[1]

            tanggal = int(parts[2])

            nominal = int(
                parts[3]
                .replace(".", "")
                .replace(",", "")
            )

            if tanggal < 1 or tanggal > 31:

                kirim_wa(
                    sender,
                    "Tanggal harus antara 1-31."
                )

                return jsonify({"status": True})

            reminder = Reminder.query.filter_by(
                nomor_wa=sender,
                nama=nama
            ).first()

            if reminder:

                reminder.tanggal = tanggal
                reminder.nominal = nominal
                reminder.aktif = True

                status = "Diperbarui"

            else:

                reminder = Reminder(

                    nomor_wa=sender,

                    nama=nama,

                    tanggal=tanggal,

                    nominal=nominal

                )

                db.session.add(reminder)

                status = "Dibuat"

            db.session.commit()

            kirim_wa(
                sender,
                f"""🔔 *Reminder {status}*
━━━━━━━━━━━━━━

📄 Tagihan
{nama.title()}

📅 Jatuh Tempo
Tanggal {tanggal}

💰 Estimasi
Rp {nominal:,.0f}

━━━━━━━━━━━━━━

Ketik *reminder*
untuk melihat seluruh reminder.
"""
            )

        except Exception as e:

            print(e)

            kirim_wa(
                sender,
                str(e)
            )

        return jsonify({"status": True})

    # =========================
    # HAPUS REMINDER
    # =========================
    if cmd.startswith("hapusreminder"):

        try:

            parts = message.lower().split()

            if len(parts) < 2:

                kirim_wa(
                    sender,
                    "Format:\n"
                    "hapusreminder listrik"
                )

                return jsonify({"status": True})

            nama = parts[1]

            reminder = Reminder.query.filter_by(
                nomor_wa=sender,
                nama=nama
            ).first()

            if not reminder:

                kirim_wa(
                    sender,
                    "Reminder tidak ditemukan."
                )

                return jsonify({"status": True})

            db.session.delete(reminder)

            db.session.commit()

            kirim_wa(
                sender,
                f"""🗑️ Reminder berhasil dihapus

    📄 {nama.title()}
    """
            )

        except Exception as e:

            print(e)

            kirim_wa(
                sender,
                str(e)
            )

        return jsonify({"status": True})

    # =========================
    # DEFAULT
    # =========================
    return jsonify({
        "status": True
    })

def progress_bar(persen):

    penuh = int(persen / 10)

    return "🟩" * penuh + "⬜" * (10 - penuh)

def ai_insight(sender):

    bulan = periode_sekarang()

    data = transaksi_user(sender).filter(
        Transaksi.tipe == "KELUAR"
    ).all()

    if not data:
        return "Belum ada data untuk dianalisis."

    total = sum(x.nominal for x in data)

    kategori = {}

    for trx in data:

        kategori.setdefault(trx.kategori, 0)

        kategori[trx.kategori] += trx.nominal

    kategori_terbesar = max(
        kategori,
        key=kategori.get
    )

    nominal = kategori[kategori_terbesar]

    persen = nominal / total * 100

    insight = []

    insight.append(
        f"📊 Pengeluaran terbesar berada pada kategori *{kategori_terbesar.title()}* ({persen:.1f}%)."
    )

    if persen > 50:

        insight.append(
            f"⚠️ Lebih dari setengah pengeluaran berasal dari {kategori_terbesar}."
        )

    elif persen > 30:

        insight.append(
            f"💡 Pengeluaran {kategori_terbesar} mulai mendominasi bulan ini."
        )

    else:

        insight.append(
            "✅ Pengeluaran masih cukup seimbang antar kategori."
        )

    return "\n".join(insight)


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


def periode_sekarang():
    return datetime.now().strftime("%Y-%m")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
