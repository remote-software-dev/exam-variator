# 🎓 Generator Variasi Soal (Exam Variator)

Otomatis mengekstrak soal ujian matematika dari PDF, membuat variasi soal yang lebih mudah dan lebih sulit dengan AI, lalu mengekspor hasilnya ke dokumen Word.

## Fitur

- **Ekstraksi semua soal** — setiap halaman PDF dirender menjadi gambar lalu diproses AI untuk mengekstrak *semua* soal (bukan hanya satu soal per halaman).
- **Variasi AI** — untuk setiap soal dibuat 2 variasi: *lebih mudah* dan *lebih sulit*, dengan 5 opsi jawaban (A–E).
- **Pemrosesan bertahap (5-by-5)** — soal diproses dalam kelompok 5. Setelah setiap kelompok, muncul popup untuk melanjutkan 5 soal berikutnya atau berhenti dan memakai hasil yang sudah ada.
- **Format matriks LaTeX yang ketat** — prompt AI mewajibkan `\begin{bmatrix} ... \end{bmatrix}` (dengan *few-shot example*) agar matriks tidak pernah dirender sebagai `|`, `||`, `∨`, atau array teks polos.
- **Instruksi kustom** — tambahkan instruksi seperti "buat penyelesaian dengan konsep dasar dan cara cepat" untuk menghasilkan `solution_by_concept` dan `solution_by_trick`.
- **Ekspor Word** — DOCX dihasilkan melalui pandoc (`--mathml`) agar LaTeX menjadi persamaan Word asli; fallback ke python-docx + latex2mathml jika pandoc tidak tersedia.
- **Pratinjau hasil** — preview soal asli dan variasi langsung di UI (render `$...$` LaTeX).

## Arsitektur Pipeline

```
PDF ──► PNG (per halaman) ──► Ekstrak semua soal (LLM vision)
        ──► Variasi 5-by-5 (LLM) ──► Ekspor DOCX + JSON sidecar
```

## Instalasi

```bash
git clone git@github.com:remote-software-dev/exam-variator.git
cd exam-variator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Salin `.env.example` ke `.env` dan isi kunci API (fallback ke Streamlit Cloud secrets juga didukung):

```bash
GROQ_API_KEY=your-key-here
```

## Menjalankan UI (Streamlit)

```bash
streamlit run app.py
```

1. Unggah PDF soal ujian.
2. (Opsional) tulis instruksi tambahan.
3. Klik **Buat Variasi**.
4. Setelah tiap 5 soal, pilih **Lanjutkan ➡️** atau **Selesai**.
5. Unduh dokumen Word hasil akhir.

## Menjalankan via CLI

```bash
python -m src.exam_generator.pipeline
```

`run_pipeline()` juga bisa dipanggil langsung dan mendukung `batch_size` serta `continue_callback(processed, total) -> bool` untuk menghentikan proses lebih awal.

## Struktur Proyek

```
app.py                          # UI Streamlit (upload, batch 5-by-5, pratinjau)
src/exam_generator/
  pipeline.py                   # ekstraksi soal, generasi variasi, orkestrasi batch
  docx_exporter.py              # ekspor DOCX (pandoc → fallback python-docx)
scripts/
  structure_questions.py        # utilitas strukturisasi soal dari teks PDF
  render_pages.py               # render halaman PDF menjadi PNG
data/
  inputs/                       # PDF masukan
  outputs/                      # DOCX, PNG halaman, JSON sidecar
```

## Model AI (fallback chain)

- **Ekstraksi:** `groq/qwen/qwen3.6-27b` → `groq/meta-llama/llama-4-scout-17b-16e-instruct` → `groq/meta-llama/llama-4-maverick-17b-128e-instruct`
- **Variasi:** `groq/llama-3.3-70b-versatile` → `openai/gpt-4o-mini`

Daftar model dapat disesuaikan di `src/exam_generator/pipeline.py`.
