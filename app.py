import io, json
from datetime import date, timedelta
import pandas as pd, streamlit as st
import db

st.set_page_config(page_title="INVENTARIS GUDANG", layout="wide")
db.init()

# ---------- RawBlock design tokens ----------
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Mono&family=Work+Sans:wght@400;600&display=swap');
html,body,[class*="css"],.stApp{font-family:'Work Sans',Arial,sans-serif;font-size:16px;line-height:1.6;color:#000;background:#fff}
h1,h2,h3{font-family:'Archivo Black',Impact,sans-serif!important;font-weight:400!important;text-transform:uppercase;letter-spacing:0}
h1{font-size:64px!important;line-height:1!important}h2{font-size:48px!important;line-height:1.05!important;border-bottom:5px solid #000;padding-bottom:8px}
h3{font-size:32px!important;line-height:1.1!important}
*{border-radius:0!important;box-shadow:none!important}
a{color:#0000FF}
section[data-testid="stSidebar"]{background:#fff;border-right:5px solid #000}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{background:#000;color:#fff;border:3px solid #000;
 text-transform:uppercase;letter-spacing:2px;padding:10px 24px;font-weight:600}
.stButton>button p,.stDownloadButton>button p,[data-testid="stFormSubmitButton"]>button p{color:inherit}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{background:#fff;color:#000;border:3px solid #000}
.stButton>button:active,[data-testid="stFormSubmitButton"]>button:active{background:#000;color:#fff;border:5px solid #000}
input,textarea,[data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="base-input"]{background:#F0F0F0!important;border:3px solid #000!important;
 font-family:'Space Mono',monospace!important;font-size:15px!important}
input:focus{outline:none!important}
label,[data-testid="stWidgetLabel"] p{font-family:'Archivo Black',sans-serif!important;font-size:14px!important;text-transform:uppercase;font-weight:400!important}
[data-testid="stMetric"],[data-testid="stForm"],[data-testid="stDataFrame"]{border:3px solid #000;padding:24px}
[data-testid="stDataFrame"]{padding:0}
.box{border:3px solid #000;padding:24px;margin:8px 0 16px}.box.err{border-color:#F00;color:#F00}.box.heavy{border-width:5px}
.mono{font-family:'Space Mono',monospace}.chip{border:2px solid;padding:2px 10px;font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase}
</style>""", unsafe_allow_html=True)

def chip(t, c="#000"): return f"<span class='chip' style='color:{c};border-color:{c}'>{t}</span>"
def flash(m, kind="ok"): st.session_state["flash"] = (m, kind)
def lbl(df, col): return {f"{r[0]} · {r[1]}": r[2] for r in df[[col[0], col[1], col[2]]].itertuples(index=False)}

# ---------- Login ----------
def login_page():
    st.title("INVENTARIS GUDANG")
    st.markdown("<div class='box heavy mono'><b>SELAMAT DATANG DI SISTEM INFORMASI INVENTARISASI BARANG</b><br>HARAP GUNAKAN MODE TERANG JIKA TYPING/TULISANNYA TIDAK TERLIHAT</br></div>", unsafe_allow_html=True)
    with st.form("login"):
        e = st.text_input("Email"); p = st.text_input("Kata sandi", type="password")
        if st.form_submit_button("MASUK"):
            u = db.login(e, p)
            if u: st.session_state["user"] = u; st.rerun()
            else: st.error("Email/kata sandi salah atau akun nonaktif.")

# ---------- Dashboard / Alert (FR-08) ----------
def alert_box():
    k = db.stok_kritis()
    if k.empty: st.markdown("<div class='box'>SEMUA STOK DI ATAS MINIMUM " + chip("AMAN", "#008000") + "</div>", unsafe_allow_html=True); return
    rows = "".join(f"<li><b>{r.nama_barang}</b> ({r.kode_barang}) — stok {r.stok} / min {r.minimum} {r.satuan}, rak {r.rak}</li>" for r in k.itertuples())
    st.markdown(f"<div class='box err heavy'><b>PERINGATAN: {len(k)} BARANG DI BAWAH/SAMA DENGAN STOK MINIMUM</b><ul>{rows}</ul></div>", unsafe_allow_html=True)

def dashboard():
    st.header("Dashboard"); alert_box()
    t = str(date.today())
    m = db.q("""SELECT (SELECT COUNT(*) FROM barang WHERE status_aktif=1) a,(SELECT COALESCE(SUM(stok_saat_ini),0) FROM barang) s,
      (SELECT COALESCE(SUM(jumlah_perubahan),0) FROM riwayat_stok WHERE jenis_mutasi='MASUK' AND date(waktu_transaksi)=?) i,
      (SELECT COALESCE(-SUM(jumlah_perubahan),0) FROM riwayat_stok WHERE jenis_mutasi='KELUAR' AND date(waktu_transaksi)=?) o""", (t, t)).iloc[0]
    c = st.columns(4); c[0].metric("Barang aktif", int(m.a)); c[1].metric("Total stok", int(m.s)); c[2].metric("Masuk hari ini", int(m.i)); c[3].metric("Keluar hari ini", int(m.o))
    st.subheader("Stok per barang"); b = db.q("SELECT nama_barang,stok_saat_ini AS stok,stok_minimum AS minimum FROM barang WHERE status_aktif=1")
    st.bar_chart(b.set_index("nama_barang"), color=["#000000", "#FF0000"])
    st.subheader("Mutasi terakhir"); st.dataframe(db.mutasi(date(2000, 1, 1), date.today()).head(10), width="stretch", hide_index=True)

def alert_page():
    st.header("Alert Stok Minimum"); alert_box(); st.dataframe(db.stok_kritis(), width="stretch", hide_index=True)

# ---------- Master (FR-02, FR-03) ----------
def master_simple(t, label):
    idc, kc, nc = db.MASTER[t]; st.header(label)
    df = db.q(f"SELECT * FROM {t} ORDER BY {kc}"); st.dataframe(df.drop(columns=[idc]), width="stretch", hide_index=True)
    opsi = {"— DATA BARU —": None, **{f"{r[0]} · {r[1]}": r[2] for r in df[[kc, nc, idc]].itertuples(index=False)}}
    cur = opsi[st.selectbox("Pilih data", list(opsi), key=f"s{t}")]; row = df[df[idc] == cur].iloc[0] if cur else None
    with st.form(f"f{t}{cur}"):
        kode = st.text_input("Kode", row[kc] if cur else ""); nama = st.text_input("Nama", row[nc] if cur else "")
        if st.form_submit_button("SIMPAN"):
            try: db.simpan_master(t, cur, kode, nama); flash("Tersimpan."); st.rerun()
            except ValueError as e: st.error(str(e))
    if cur: aksi_status(t, idc, cur, row.status_aktif)

def aksi_status(t, idc, cur, aktif):
    a, b, _ = st.columns([1, 1, 3])
    if a.button("NONAKTIFKAN" if aktif else "AKTIFKAN", key=f"t{t}{cur}"): db.toggle(t, idc, cur); flash("Status diubah."); st.rerun()
    if b.button("HAPUS", key=f"h{t}{cur}"):
        try: db.hapus(t, idc, cur); flash("Dihapus."); st.rerun()
        except ValueError as e: st.error(str(e))

def master_barang():
    st.header("Master Barang")
    df = db.q("""SELECT b.*,k.nama_kategori kategori,s.nama_supplier supplier FROM barang b JOIN kategori k USING(id_kategori) JOIN supplier s USING(id_supplier) ORDER BY kode_barang""")
    st.dataframe(df.drop(columns=["id_barang", "id_kategori", "id_supplier"]), width="stretch", hide_index=True)
    opsi = {"— BARANG BARU —": None, **{f"{r[0]} · {r[1]}": r[2] for r in df[["kode_barang", "nama_barang", "id_barang"]].itertuples(index=False)}}
    cur = opsi[st.selectbox("Pilih barang", list(opsi))]; r = df[df.id_barang == cur].iloc[0] if cur else None
    kat = {f"{a} · {b}": c for a, b, c in db.q("SELECT kode_kategori,nama_kategori,id_kategori FROM kategori WHERE status_aktif=1").values}
    sup = {f"{a} · {b}": c for a, b, c in db.q("SELECT kode_supplier,nama_supplier,id_supplier FROM supplier WHERE status_aktif=1").values}
    with st.form(f"fb{cur}"):
        c1, c2 = st.columns(2)
        kode = c1.text_input("Kode barang", r.kode_barang if cur else ""); nama = c2.text_input("Nama barang", r.nama_barang if cur else "")
        kk = c1.selectbox("Kategori", list(kat), index=list(kat.values()).index(r.id_kategori) if cur and r.id_kategori in kat.values() else 0)
        ss = c2.selectbox("Supplier", list(sup), index=list(sup.values()).index(r.id_supplier) if cur and r.id_supplier in sup.values() else 0)
        sat = c1.text_input("Satuan", r.satuan if cur else ""); rak = c2.text_input("Lokasi rak", (r.lokasi_rak or "") if cur else "")
        smin = c1.number_input("Stok minimum", 0, value=int(r.stok_minimum) if cur else 0)
        st.caption("Stok awal = 0; isi lewat Barang Masuk / Impor Excel agar tercatat di audit.")
        if st.form_submit_button("SIMPAN"):
            try: db.simpan_barang(cur, kode, nama, kat[kk], sup[ss], sat, rak, int(smin)); flash("Barang tersimpan."); st.rerun()
            except ValueError as e: st.error(str(e))
    if cur:
        aksi_status("barang", "id_barang", cur, r.status_aktif)
        st.subheader("Label barcode")
        try:
            png = label_png(r.kode_barang); st.image(png, width=320)
            st.download_button("UNDUH LABEL (.PNG)", png, f"label_{r.kode_barang}.png", "image/png")
        except Exception: st.caption("Kode ini tidak bisa dibuat Code128.")

def master_pengguna():
    st.header("Akun Pengguna"); d = db.q("SELECT id_pengguna,nama_lengkap,email,peran,status_aktif FROM pengguna")
    st.dataframe(d.drop(columns="id_pengguna"), width="stretch", hide_index=True)
    with st.form("up"):
        n = st.text_input("Nama lengkap"); e = st.text_input("Email"); p = st.text_input("Kata sandi", type="password"); r = st.selectbox("Peran", ["ADMIN", "PETUGAS", "MANAJER"])
        if st.form_submit_button("TAMBAH AKUN"):
            try:
                if not (n and e and len(p) >= 6): raise ValueError("Lengkapi data; sandi min. 6 karakter")
                db.ex("INSERT INTO pengguna(nama_lengkap,email,kata_sandi_hash,peran) VALUES(?,?,?,?)", (n, e.strip().lower(), db.hash_pw(p), r)); flash("Akun dibuat."); st.rerun()
            except ValueError as ex_: st.error(str(ex_))
    sel = st.selectbox("Aktif/nonaktifkan akun", d.id_pengguna, format_func=lambda i: d.set_index("id_pengguna").loc[i, "email"])
    if st.button("UBAH STATUS AKUN"):
        if sel == st.session_state["user"]["id_pengguna"]: st.error("Tidak bisa menonaktifkan akun sendiri.")
        else: db.toggle("pengguna", "id_pengguna", sel); flash("Status diubah."); st.rerun()

# ---------- Impor Excel (FR-05) ----------
def xlsx_bytes(df, sheet="Data"):
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w: df.to_excel(w, index=False, sheet_name=sheet)
    return b.getvalue()

def impor():
    st.header("Impor Massal Excel")
    st.download_button("UNDUH TEMPLATE .XLSX", xlsx_bytes(db.template_df(), "Template"), "template_impor_barang.xlsx")
    f = st.file_uploader("Unggah file .xlsx", type=["xlsx"])
    if f:
        try: v = db.validasi(pd.read_excel(f, dtype=str))
        except Exception as e: st.error(f"File tidak dapat dibaca: {e}"); return
        nv, ne = (v.status == "VALID").sum(), (v.status == "ERROR").sum()
        st.markdown(f"<div class='box'>{chip('VALID ' + str(nv), '#008000')} {chip('ERROR ' + str(ne), '#FF0000')}</div>", unsafe_allow_html=True)
        st.dataframe(v[["baris", "status", "alasan", "kode_barang", "nama_barang", "kode_kategori", "kode_supplier", "satuan", "lokasi_rak", "stok_awal", "stok_minimum"]]
                     .style.apply(lambda r: ["color:#FF0000" if r.status == "ERROR" else "color:#008000"] * len(r), axis=1), width="stretch", hide_index=True)
        if st.button("KONFIRMASI IMPOR BARIS VALID", disabled=nv == 0):
            try: s, g = db.konfirmasi_impor(v, f.name, st.session_state["user"]["id_pengguna"]); flash(f"Impor selesai: {s} sukses, {g} dilewati (error)."); st.rerun()
            except Exception as e: st.error(f"Impor dibatalkan (rollback): {e}")
    st.subheader("Log impor"); st.dataframe(db.q("SELECT * FROM log_impor ORDER BY id_import DESC"), width="stretch", hide_index=True)

# ---------- Scan & Transaksi (FR-04, FR-06, FR-07) ----------
def decode_image(file):
    import zxingcpp
    from PIL import Image
    r = zxingcpp.read_barcodes(Image.open(io.BytesIO(file.getvalue())))
    return r[0].text if r else ""

def label_png(kode):
    import barcode
    from barcode.writer import ImageWriter
    buf = io.BytesIO(); barcode.get("code128", kode, writer=ImageWriter()).write(buf, {"module_height": 12, "font_size": 8, "text_distance": 3})
    return buf.getvalue()

def kartu_barang(b):
    st.markdown(f"<div class='box heavy'><h3 style='margin:0'>{b.nama_barang}</h3><span class='mono'>{b.kode_barang}</span><br>"
                f"SATUAN: <b>{b.satuan}</b> · RAK: <b>{b.lokasi_rak}</b> · STOK SAAT INI: <b>{b.stok_saat_ini}</b> · MIN: {b.stok_minimum}</div>", unsafe_allow_html=True)

def tambah(jenis, b, src):
    cart = st.session_state.setdefault(f"cart_{jenis}", [])
    kartu_barang(b)
    j = st.number_input("Jumlah", 1, value=1, key=f"j{jenis}{b.id_barang}{src}")
    if st.button("TAMBAHKAN KE DAFTAR", key=f"a{jenis}{b.id_barang}{src}"):
        cart.append(dict(id=int(b.id_barang), kode=b.kode_barang, nama=b.nama_barang, jumlah=int(j), src=src)); st.session_state["scan_n"] = st.session_state.get("scan_n", 0) + 1; st.rerun()

def daftar(jenis):
    cart = st.session_state.setdefault(f"cart_{jenis}", [])
    st.subheader(f"Daftar barang {jenis.lower()}")
    if not cart: st.caption("Belum ada barang."); return
    st.dataframe(pd.DataFrame(cart)[["kode", "nama", "jumlah", "src"]], width="stretch", hide_index=True)
    tujuan = st.text_input("Penerima / tujuan") if jenis == "KELUAR" else ""
    a, b, _ = st.columns([1, 1, 3])
    if a.button(f"SIMPAN TRANSAKSI {jenis}"):
        sumber = "SCAN" if any(c["src"] == "SCAN" for c in cart) else "MANUAL"
        try:
            no = db.catat(jenis, [(c["id"], c["jumlah"]) for c in cart], st.session_state["user"]["id_pengguna"], sumber, tujuan)
            st.session_state[f"cart_{jenis}"] = []; flash(f"Transaksi {no} tersimpan; stok & audit diperbarui."); st.rerun()
        except ValueError as e: st.error(str(e))
    if b.button("KOSONGKAN"): st.session_state[f"cart_{jenis}"] = []; st.rerun()

def scan():
    from streamlit_qrcode_scanner import qrcode_scanner
    st.header("Scan Barcode / QR")
    jenis = st.radio("Jenis transaksi", ["MASUK", "KELUAR"], horizontal=True)
    n = st.session_state.setdefault("scan_n", 0)
    st.markdown("<div class='box heavy'><b>ARAHKAN BARCODE / QR KE KAMERA</b> — terbaca otomatis, tanpa perlu menekan tombol.</div>", unsafe_allow_html=True)
    kode = qrcode_scanner(key=f"scanner_{n}") or ""
    with st.expander("Kamera bermasalah? Pakai foto, scanner USB, atau ketik manual"):
        img = st.camera_input("Foto barcode/QR", key=f"cam_{n}")
        foto = decode_image(img) if img else ""
        if img and not foto: st.warning("Barcode tidak terdeteksi pada foto. Coba lebih dekat/terang.")
        manual = st.text_input("Kode barang (scanner USB: scan lalu otomatis Enter)", key=f"kode_scan_{n}").strip()
    kode = manual or foto or kode
    if kode: st.markdown(f"<div class='box mono'>KODE TERBACA: <b>{kode}</b></div>", unsafe_allow_html=True)
    if kode:
        b = db.cari(kode)
        if b is not None: tambah(jenis, b, "SCAN")
        else:
            st.markdown(f"<div class='box err'>KODE <b>{kode}</b> BELUM TERDAFTAR — daftarkan cepat di bawah.</div>", unsafe_allow_html=True)
            kat = {f"{a} · {n}": i for a, n, i in db.q("SELECT kode_kategori,nama_kategori,id_kategori FROM kategori WHERE status_aktif=1").values}
            sup = {f"{a} · {n}": i for a, n, i in db.q("SELECT kode_supplier,nama_supplier,id_supplier FROM supplier WHERE status_aktif=1").values}
            with st.form("qr"):
                nama = st.text_input("Nama barang"); k = st.selectbox("Kategori", list(kat)); s = st.selectbox("Supplier", list(sup))
                sat = st.text_input("Satuan"); rak = st.text_input("Lokasi rak"); mn = st.number_input("Stok minimum", 0)
                if st.form_submit_button("DAFTARKAN BARANG"):
                    try: db.simpan_barang(None, kode, nama, kat[k], sup[s], sat, rak, int(mn)); flash("Barang terdaftar. Scan ulang untuk lanjut."); st.rerun()
                    except ValueError as e: st.error(str(e))
    daftar(jenis)

def manual(jenis):
    st.header(f"Barang {jenis.title()}")
    b = db.q("SELECT b.*,k.nama_kategori FROM barang b JOIN kategori k USING(id_kategori) WHERE b.status_aktif=1 ORDER BY nama_barang")
    pil = st.selectbox("Pilih barang", b.index, format_func=lambda i: f"{b.kode_barang[i]} · {b.nama_barang[i]}")
    tambah(jenis, b.loc[pil], "MANUAL"); daftar(jenis)

# ---------- Laporan (FR-09) ----------
def laporan(judul, ekspor):
    st.header(judul)
    c = st.columns(4); d1 = c[0].date_input("Dari", date.today() - timedelta(days=30)); d2 = c[1].date_input("Sampai", date.today())
    kat = {"SEMUA": None, **{n: i for n, i in db.q("SELECT nama_kategori,id_kategori FROM kategori").values}}
    rak = ["SEMUA"] + db.q("SELECT DISTINCT lokasi_rak FROM barang ORDER BY 1").lokasi_rak.dropna().tolist()
    k = c[2].selectbox("Kategori", list(kat)); r = c[3].selectbox("Lokasi rak", rak)
    df = db.mutasi(d1, d2, kat[k], None if r == "SEMUA" else r)
    st.dataframe(df, width="stretch", hide_index=True)
    if ekspor:
        a, b, _ = st.columns([1, 1, 3])
        a.download_button("EKSPOR .XLSX", xlsx_bytes(df, "Mutasi"), "laporan_mutasi.xlsx")
        b.download_button("EKSPOR .CSV", df.to_csv(index=False).encode("utf-8-sig"), "laporan_mutasi.csv", "text/csv")

# ---------- Router berbasis peran (FR-01) ----------
MENU = {
 "ADMIN": {"Dashboard": dashboard, "Kategori": lambda: master_simple("kategori", "Kategori"), "Supplier": lambda: master_simple("supplier", "Supplier"),
           "Master Barang": master_barang, "Impor Excel": impor, "Akun Pengguna": master_pengguna, "Laporan": lambda: laporan("Laporan Mutasi", False)},
 "PETUGAS": {"Scan Barcode/QR": scan, "Barang Masuk": lambda: manual("MASUK"), "Barang Keluar": lambda: manual("KELUAR")},
 "MANAJER": {"Dashboard": dashboard, "Alert Stok": alert_page, "Riwayat Audit": lambda: laporan("Riwayat Audit", False), "Ekspor Laporan": lambda: laporan("Ekspor Laporan", True)},
}

u = st.session_state.get("user")
if not u: login_page(); st.stop()
with st.sidebar:
    st.markdown(f"### MENU\n<span class='mono'>{u['nama_lengkap']}</span><br>{chip(u['peran'])}", unsafe_allow_html=True)
    page = st.radio("Navigasi", list(MENU[u["peran"]]), label_visibility="collapsed")
    if st.button("KELUAR"): st.session_state.clear(); st.rerun()
if "flash" in st.session_state:
    m, kd = st.session_state.pop("flash"); (st.success if kd == "ok" else st.error)(m)
MENU[u["peran"]][page]()
