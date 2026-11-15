"""Lapisan data + service: skema, seed, transaksi atomik, validator impor."""
import sqlite3, hashlib, secrets, json
from datetime import date, datetime
import pandas as pd

DB = "inventaris.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS pengguna(id_pengguna INTEGER PRIMARY KEY AUTOINCREMENT, nama_lengkap TEXT NOT NULL,
 email TEXT NOT NULL UNIQUE, kata_sandi_hash TEXT NOT NULL, peran TEXT NOT NULL CHECK(peran IN('ADMIN','PETUGAS','MANAJER')),
 status_aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS kategori(id_kategori INTEGER PRIMARY KEY AUTOINCREMENT, kode_kategori TEXT NOT NULL UNIQUE,
 nama_kategori TEXT NOT NULL, status_aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS supplier(id_supplier INTEGER PRIMARY KEY AUTOINCREMENT, kode_supplier TEXT NOT NULL UNIQUE,
 nama_supplier TEXT NOT NULL, status_aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS barang(id_barang INTEGER PRIMARY KEY AUTOINCREMENT, kode_barang TEXT NOT NULL UNIQUE,
 nama_barang TEXT NOT NULL, id_kategori INTEGER NOT NULL REFERENCES kategori(id_kategori),
 id_supplier INTEGER NOT NULL REFERENCES supplier(id_supplier), satuan TEXT NOT NULL, lokasi_rak TEXT,
 stok_saat_ini INTEGER NOT NULL DEFAULT 0 CHECK(stok_saat_ini>=0), stok_minimum INTEGER NOT NULL DEFAULT 0 CHECK(stok_minimum>=0),
 status_aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS transaksi_masuk(id_masuk INTEGER PRIMARY KEY AUTOINCREMENT, nomor_masuk TEXT NOT NULL UNIQUE,
 tanggal_masuk TEXT NOT NULL, id_pengguna INTEGER NOT NULL REFERENCES pengguna(id_pengguna),
 sumber_input TEXT NOT NULL CHECK(sumber_input IN('SCAN','EXCEL','MANUAL')));
CREATE TABLE IF NOT EXISTS detail_barang_masuk(id_detail INTEGER PRIMARY KEY AUTOINCREMENT,
 id_masuk INTEGER NOT NULL REFERENCES transaksi_masuk(id_masuk), id_barang INTEGER NOT NULL REFERENCES barang(id_barang),
 jumlah INTEGER NOT NULL CHECK(jumlah>0));
CREATE TABLE IF NOT EXISTS transaksi_keluar(id_keluar INTEGER PRIMARY KEY AUTOINCREMENT, nomor_keluar TEXT NOT NULL UNIQUE,
 tanggal_keluar TEXT NOT NULL, id_pengguna INTEGER NOT NULL REFERENCES pengguna(id_pengguna), penerima_tujuan TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS detail_barang_keluar(id_detail INTEGER PRIMARY KEY AUTOINCREMENT,
 id_keluar INTEGER NOT NULL REFERENCES transaksi_keluar(id_keluar), id_barang INTEGER NOT NULL REFERENCES barang(id_barang),
 jumlah INTEGER NOT NULL CHECK(jumlah>0));
CREATE TABLE IF NOT EXISTS riwayat_stok(id_riwayat INTEGER PRIMARY KEY AUTOINCREMENT,
 id_barang INTEGER NOT NULL REFERENCES barang(id_barang), jenis_mutasi TEXT NOT NULL CHECK(jenis_mutasi IN('MASUK','KELUAR','KOREKSI')),
 stok_sebelum INTEGER NOT NULL, jumlah_perubahan INTEGER NOT NULL, stok_sesudah INTEGER NOT NULL, nomor_referensi TEXT,
 id_pengguna INTEGER NOT NULL REFERENCES pengguna(id_pengguna), waktu_transaksi TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS log_impor(id_import INTEGER PRIMARY KEY AUTOINCREMENT, nama_file TEXT NOT NULL,
 jumlah_sukses INTEGER NOT NULL, jumlah_gagal INTEGER NOT NULL, ringkasan_error TEXT, waktu_impor TEXT NOT NULL);
"""
MASTER = {"kategori": ("id_kategori", "kode_kategori", "nama_kategori"),
          "supplier": ("id_supplier", "kode_supplier", "nama_supplier")}

def now(): return datetime.now().isoformat(sep=" ", timespec="seconds")

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.isolation_level = None
    c.execute("PRAGMA foreign_keys=ON"); return c

def q(sql, p=()):
    c = conn()
    try: return pd.read_sql_query(sql, c, params=p)
    finally: c.close()

def ex(sql, p=()):
    c = conn()
    try: return c.execute(sql, p).lastrowid
    except sqlite3.IntegrityError as e: raise ValueError(f"Data ditolak database: {e}")
    finally: c.close()

# ---------- auth ----------
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100_000).hex()}"

def login(email, pw):
    d = q("SELECT * FROM pengguna WHERE email=? AND status_aktif=1", (email.strip().lower(),))
    if d.empty: return None
    r = d.iloc[0]
    return r.to_dict() if hash_pw(pw, r.kata_sandi_hash.split("$")[0]) == r.kata_sandi_hash else None

# ---------- master ----------
def simpan_master(t, cur, kode, nama):
    idc, kc, nc = MASTER[t]
    if not kode.strip() or not nama.strip(): raise ValueError("Kode dan nama wajib diisi")
    if cur: ex(f"UPDATE {t} SET {kc}=?,{nc}=? WHERE {idc}=?", (kode.strip(), nama.strip(), cur))
    else: ex(f"INSERT INTO {t}({kc},{nc}) VALUES(?,?)", (kode.strip(), nama.strip()))

def simpan_barang(cur, kode, nama, idk, ids, satuan, rak, smin):
    if not (kode.strip() and nama.strip() and satuan.strip()): raise ValueError("Kode, nama, satuan wajib diisi")
    if cur: ex("UPDATE barang SET kode_barang=?,nama_barang=?,id_kategori=?,id_supplier=?,satuan=?,lokasi_rak=?,stok_minimum=? WHERE id_barang=?",
               (kode.strip(), nama.strip(), idk, ids, satuan.strip(), rak.strip(), smin, cur))
    else: return ex("INSERT INTO barang(kode_barang,nama_barang,id_kategori,id_supplier,satuan,lokasi_rak,stok_minimum) VALUES(?,?,?,?,?,?,?)",
                    (kode.strip(), nama.strip(), idk, ids, satuan.strip(), rak.strip(), smin))

def toggle(t, idc, i): ex(f"UPDATE {t} SET status_aktif=1-status_aktif WHERE {idc}=?", (i,))

def hapus(t, idc, i):
    try: ex(f"DELETE FROM {t} WHERE {idc}=?", (i,))
    except ValueError: raise ValueError("Sudah punya relasi/riwayat transaksi — tidak bisa dihapus, gunakan NONAKTIFKAN.")

def cari(kode):
    d = q("""SELECT b.*,k.nama_kategori FROM barang b JOIN kategori k USING(id_kategori)
             WHERE b.kode_barang=? AND b.status_aktif=1""", (kode.strip(),))
    return None if d.empty else d.iloc[0]

# ---------- transaksi atomik (FR-06, FR-07, FR-10) ----------
def _nomor(c, tbl, col, pre):
    p = f"{pre}-{date.today().year}-"
    n = c.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col} LIKE ?", (p + "%",)).fetchone()[0] + 1
    return f"{p}{n:03d}"

def _mutasi(c, idb, delta, jenis, uid, ref):
    r = c.execute("SELECT nama_barang,stok_saat_ini,status_aktif FROM barang WHERE id_barang=?", (idb,)).fetchone()
    if not r: raise ValueError("Barang tidak ditemukan")
    if not r["status_aktif"]: raise ValueError(f"Barang '{r['nama_barang']}' nonaktif")
    sb = r["stok_saat_ini"]; sa = sb + delta
    if sa < 0: raise ValueError(f"DITOLAK: stok '{r['nama_barang']}' tidak cukup (tersedia {sb}, diminta {-delta})")
    c.execute("UPDATE barang SET stok_saat_ini=? WHERE id_barang=?", (sa, idb))
    c.execute("""INSERT INTO riwayat_stok(id_barang,jenis_mutasi,stok_sebelum,jumlah_perubahan,stok_sesudah,nomor_referensi,id_pengguna,waktu_transaksi)
                 VALUES(?,?,?,?,?,?,?,?)""", (idb, jenis, sb, delta, sa, ref, uid, now()))

def _catat(c, jenis, items, uid, sumber, tujuan):
    if not items: raise ValueError("Daftar barang kosong")
    if any(j <= 0 for _, j in items): raise ValueError("Jumlah harus lebih dari 0")
    masuk = jenis == "MASUK"
    if not masuk and not tujuan.strip(): raise ValueError("Penerima/tujuan wajib diisi")
    if masuk:
        no = _nomor(c, "transaksi_masuk", "nomor_masuk", "IN")
        h = c.execute("INSERT INTO transaksi_masuk(nomor_masuk,tanggal_masuk,id_pengguna,sumber_input) VALUES(?,?,?,?)",
                      (no, now(), uid, sumber)).lastrowid
    else:
        no = _nomor(c, "transaksi_keluar", "nomor_keluar", "OUT")
        h = c.execute("INSERT INTO transaksi_keluar(nomor_keluar,tanggal_keluar,id_pengguna,penerima_tujuan) VALUES(?,?,?,?)",
                      (no, now(), uid, tujuan.strip())).lastrowid
    for idb, j in items:
        if masuk: c.execute("INSERT INTO detail_barang_masuk(id_masuk,id_barang,jumlah) VALUES(?,?,?)", (h, idb, j))
        else: c.execute("INSERT INTO detail_barang_keluar(id_keluar,id_barang,jumlah) VALUES(?,?,?)", (h, idb, j))
        _mutasi(c, idb, j if masuk else -j, jenis, uid, no)
    return no

def catat(jenis, items, uid, sumber="MANUAL", tujuan=""):
    c = conn()
    try:
        c.execute("BEGIN"); no = _catat(c, jenis, items, uid, sumber, tujuan); c.execute("COMMIT"); return no
    except Exception:
        c.execute("ROLLBACK"); raise
    finally: c.close()

# ---------- impor Excel (FR-05) ----------
COLS = ["kode_barang", "nama_barang", "kode_kategori", "kode_supplier", "satuan", "lokasi_rak", "stok_awal", "stok_minimum"]
def template_df():
    return pd.DataFrame([["BRG-100", "Contoh Barang", "ATK", "SUP-01", "pcs", "A-01", 10, 5]], columns=COLS)

def _int(v):
    if v is None or pd.isna(v) or str(v).strip() == "": return 0
    f = float(v)
    if f != int(f) or f < 0: raise ValueError
    return int(f)

def validasi(df):
    df = df.copy(); df.columns = [str(c).strip().lower() for c in df.columns]
    miss = [c for c in COLS if c not in df.columns]
    if miss: raise ValueError("Kolom template tidak ditemukan: " + ", ".join(miss))
    kat = dict(q("SELECT kode_kategori,id_kategori FROM kategori WHERE status_aktif=1").values)
    sup = dict(q("SELECT kode_supplier,id_supplier FROM supplier WHERE status_aktif=1").values)
    ada = set(q("SELECT kode_barang FROM barang").kode_barang)
    seen, out = {}, []
    for i, r in df.iterrows():
        e = []; kode = "" if pd.isna(r["kode_barang"]) else str(r["kode_barang"]).strip()
        for c in ["kode_barang", "nama_barang", "kode_kategori", "kode_supplier", "satuan"]:
            if pd.isna(r[c]) or str(r[c]).strip() == "": e.append(f"kolom '{c}' kosong")
        if kode:
            if kode in ada: e.append("kode_barang sudah ada di database")
            if kode in seen: e.append(f"kode_barang ganda di file (sama dgn baris {seen[kode]})")
            else: seen[kode] = i + 2
        kc, sc = str(r["kode_kategori"]).strip(), str(r["kode_supplier"]).strip()
        if kc and not pd.isna(r["kode_kategori"]) and kc not in kat: e.append(f"kategori '{kc}' tidak terdaftar/nonaktif")
        if sc and not pd.isna(r["kode_supplier"]) and sc not in sup: e.append(f"supplier '{sc}' tidak terdaftar/nonaktif")
        try: sa = _int(r["stok_awal"])
        except Exception: sa = 0; e.append("stok_awal harus bilangan bulat >= 0")
        try: sm = _int(r["stok_minimum"])
        except Exception: sm = 0; e.append("stok_minimum harus bilangan bulat >= 0")
        out.append(dict(baris=i + 2, status="ERROR" if e else "VALID", alasan="; ".join(e), kode_barang=kode,
                        nama_barang=str(r["nama_barang"]).strip(), kode_kategori=kc, kode_supplier=sc, satuan=str(r["satuan"]).strip(),
                        lokasi_rak="" if pd.isna(r["lokasi_rak"]) else str(r["lokasi_rak"]).strip(),
                        stok_awal=sa, stok_minimum=sm, id_kategori=kat.get(kc), id_supplier=sup.get(sc)))
    return pd.DataFrame(out)

def konfirmasi_impor(v, nama_file, uid):
    ok, bad = v[v.status == "VALID"], v[v.status == "ERROR"]
    ringkasan = json.dumps([{"baris": int(r.baris), "kode_barang": r.kode_barang, "error": r.alasan} for r in bad.itertuples()], ensure_ascii=False)
    c = conn()
    try:
        c.execute("BEGIN"); items = []
        for r in ok.itertuples():
            idb = c.execute("INSERT INTO barang(kode_barang,nama_barang,id_kategori,id_supplier,satuan,lokasi_rak,stok_minimum) VALUES(?,?,?,?,?,?,?)",
                            (r.kode_barang, r.nama_barang, int(r.id_kategori), int(r.id_supplier), r.satuan, r.lokasi_rak, int(r.stok_minimum))).lastrowid
            if r.stok_awal > 0: items.append((idb, int(r.stok_awal)))
        if items: _catat(c, "MASUK", items, uid, "EXCEL", "")
        c.execute("INSERT INTO log_impor(nama_file,jumlah_sukses,jumlah_gagal,ringkasan_error,waktu_impor) VALUES(?,?,?,?,?)",
                  (nama_file, len(ok), len(bad), ringkasan, now()))
        c.execute("COMMIT"); return len(ok), len(bad)
    except Exception:
        c.execute("ROLLBACK"); raise
    finally: c.close()

# ---------- laporan (FR-09) ----------
def mutasi(d1, d2, idk=None, rak=None, jenis=None):
    sql = """SELECT r.waktu_transaksi AS waktu, r.nomor_referensi AS referensi, b.kode_barang, b.nama_barang, k.nama_kategori AS kategori,
      b.lokasi_rak AS rak, r.jenis_mutasi AS jenis, r.stok_sebelum, r.jumlah_perubahan AS perubahan, r.stok_sesudah, p.nama_lengkap AS pelaku
      FROM riwayat_stok r JOIN barang b ON b.id_barang=r.id_barang JOIN kategori k ON k.id_kategori=b.id_kategori
      JOIN pengguna p ON p.id_pengguna=r.id_pengguna WHERE date(r.waktu_transaksi) BETWEEN ? AND ?"""
    p = [str(d1), str(d2)]
    if idk: sql += " AND b.id_kategori=?"; p.append(idk)
    if rak: sql += " AND b.lokasi_rak=?"; p.append(rak)
    if jenis: sql += " AND r.jenis_mutasi=?"; p.append(jenis)
    return q(sql + " ORDER BY r.id_riwayat DESC", tuple(p))

def stok_kritis():
    return q("""SELECT b.kode_barang,b.nama_barang,k.nama_kategori AS kategori,b.lokasi_rak AS rak,b.stok_saat_ini AS stok,b.stok_minimum AS minimum,b.satuan
                FROM barang b JOIN kategori k USING(id_kategori) WHERE b.status_aktif=1 AND b.stok_saat_ini<=b.stok_minimum ORDER BY b.stok_saat_ini""")

# ---------- init + seed ----------
def init():
    c = conn(); c.executescript(SCHEMA)
    empty = c.execute("SELECT COUNT(*) FROM pengguna").fetchone()[0] == 0; c.close()
    if not empty: return
    for n, e, pw, r in [("Budi Admin", "admin@gudang.id", "admin123", "ADMIN"), ("Sari Petugas", "petugas@gudang.id", "petugas123", "PETUGAS"),
                        ("Pak Manajer", "manajer@gudang.id", "manajer123", "MANAJER")]:
        ex("INSERT INTO pengguna(nama_lengkap,email,kata_sandi_hash,peran) VALUES(?,?,?,?)", (n, e, hash_pw(pw), r))
    for k, n in [("ATK", "Alat Tulis Kantor"), ("ELK", "Elektronik"), ("KMB", "Kemasan & Pengiriman")]:
        ex("INSERT INTO kategori(kode_kategori,nama_kategori) VALUES(?,?)", (k, n))
    for k, n in [("SUP-01", "PT Sinar Kertas"), ("SUP-02", "CV Teknik Maju"), ("SUP-03", "UD Kemas Jaya")]:
        ex("INSERT INTO supplier(kode_supplier,nama_supplier) VALUES(?,?)", (k, n))
    brg = [("BRG-001", "Kertas A4 80gsm", 1, 1, "rim", "A-01", 20, 50), ("BRG-002", "Pulpen Hitam", 1, 1, "box", "A-02", 10, 30),
           ("BRG-003", "Kabel LAN Cat6 5m", 2, 2, "pcs", "B-01", 8, 15), ("BRG-004", "Mouse Wireless", 2, 2, "pcs", "B-02", 5, 12),
           ("BRG-005", "Toner Printer 12A", 2, 2, "pcs", "B-03", 4, 6), ("BRG-006", "Lakban Bening", 3, 3, "roll", "C-01", 15, 40),
           ("BRG-007", "Kardus 30x30", 3, 3, "pcs", "C-02", 50, 120), ("BRG-008", "Bubble Wrap 50m", 3, 3, "roll", "C-03", 5, 9)]
    ids = [simpan_barang(None, b[0], b[1], b[2], b[3], b[4], b[5], b[6]) for b in brg]
    catat("MASUK", [(i, b[7]) for i, b in zip(ids, brg)], 2, "MANUAL")
    catat("KELUAR", [(ids[0], 8), (ids[2], 3), (ids[6], 20), (ids[3], 8), (ids[4], 4)], 2, tujuan="Divisi Operasional")
