# Sistem Informasi Inventarisasi Barang (Streamlit + SQLite)
    pip install -r requirements.txt
    streamlit run app.py
DB `inventaris.db` + data dummy dibuat otomatis saat pertama jalan (hapus file untuk reset).
Akun demo: admin@gudang.id/admin123 · petugas@gudang.id/petugas123 · manajer@gudang.id/manajer123
Desain: RawBlock (DESIGN.md). Scan: kamera live (html5-qrcode) + foto (zxing-cpp). Label barcode Code128 ada di Master Barang. Berkas: db.py (skema, service atomik, validator impor), app.py (UI + RBAC).
c