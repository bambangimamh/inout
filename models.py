from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    nama = db.Column(db.String(100), nullable=False)

    nomor_wa = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True
    )

    aktif = db.Column(
        db.Boolean,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

class Transaksi(db.Model):

    __tablename__ = "transaksi"

    id = db.Column(db.Integer, primary_key=True)

    tanggal = db.Column(db.DateTime)

    tipe = db.Column(db.String(20))

    nominal = db.Column(db.Integer)

    kategori = db.Column(db.String(50))

    subkategori = db.Column(db.String(100))

    keterangan = db.Column(db.String(255))

    nomor_wa = db.Column(db.String(30))

class Budget(db.Model):

    __tablename__ = "budget"

    id = db.Column(db.Integer, primary_key=True)

    nomor_wa = db.Column(db.String(30), nullable=False, index=True)

    kategori = db.Column(db.String(100), nullable=False)

    nominal = db.Column(db.Integer, nullable=False)

    periode = db.Column(db.String(7), nullable=False)   # contoh: 2026-06

    dibuat = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "nomor_wa",
            "kategori",
            "periode",
            name="uq_budget"
        ),
    )

class Reminder(db.Model):

    __tablename__ = "reminder"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nomor_wa = db.Column(
        db.String(30),
        nullable=False,
        index=True
    )

    nama = db.Column(
        db.String(100),
        nullable=False
    )

    nominal = db.Column(
        db.Integer,
        default=0
    )

    tanggal = db.Column(
        db.Integer,
        nullable=False
    )

    aktif = db.Column(
        db.Boolean,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
