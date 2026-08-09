import json as _json
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

st.set_page_config(page_title="Generator Variasi Soal", layout="centered")
st.title("🎓 Generator Variasi Soal")
st.markdown("Unggah PDF soal ujian untuk mengekstrak semua soal secara otomatis, membuat variasi soal yang lebih mudah atau lebih sulit, dan mengunduh dokumen hasil dalam bentuk Word.")

PDF_PATH = "data/inputs/uploaded_exam.pdf"
OUTPUT_PATH = "data/outputs/final_pipeline_result.docx"


def _render_preview():
    """Live preview of the collected results (st.markdown renders $...$ LaTeX)."""
    results_json = OUTPUT_PATH.rsplit(".", 1)[0] + ".json"
    if not os.path.exists(results_json):
        return
    with open(results_json, encoding="utf-8") as f:
        results = _json.load(f)

    st.divider()
    st.subheader("📄 Pratinjau Hasil")
    for idx, q in enumerate(results.get("questions", []), 1):
        page_note = f" (Halaman {q['page']})" if q.get("page") else ""
        st.markdown(f"### Soal {idx}{page_note}")
        original = q.get("original", {})
        if original.get("id"):
            st.caption(f"ID: {original['id']}")
        st.markdown(original.get("question_text", ""))
        options = original.get("options") or []
        if options:
            for i, opt in enumerate(options):
                st.markdown(f"{chr(65 + i)}. {opt}")
        for variant in ("easier", "harder"):
            label = "Mudah" if variant == "easier" else "Sulit"
            v = q.get("variations", {}).get(variant)
            if not v:
                continue
            st.markdown(f"**Variasi Lebih {label}**\n\n{v.get('question_text', '')}")
            for i, opt in enumerate(v.get("options") or []):
                st.markdown(f"- **{chr(65 + i)}.** {opt}")
            for key, title in (("solution_by_concept", "Penyelesaian (Konsep Dasar)"),
                               ("solution_by_trick", "Penyelesaian (Cara Cepat/Trik)")):
                solution = v.get(key)
                if solution:
                    st.markdown(f"*{title}*\n\n{solution}")


def _render_download_and_preview():
    """Offer the finished Word download and preview the results."""
    if os.path.exists(OUTPUT_PATH):
        st.success("✅ Pemrosesan selesai!")
        with open(OUTPUT_PATH, "rb") as file:
            st.download_button(
                label="⬇️ Download Hasil Akhir Dokumen Word",
                data=file,
                file_name="Bank_Soal_Variasi.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
    _render_preview()


uploaded_file = st.file_uploader("Pilih file PDF", type="pdf")

if uploaded_file is not None:
    with open(PDF_PATH, "wb") as f:
        f.write(uploaded_file.getbuffer())

    custom_instruction = st.text_area(
        "Instruksi Tambahan (Opsional)",
        placeholder="Contoh: Buat penyelesaian dengan konsep dasar, atau jelaskan cara cepat/trik mengerjakan soal ini...",
    )

    if st.button("🚀 Buat Variasi", type="primary", use_container_width=True):
        with st.status("🔄 Memproses Soal...", expanded=True) as status:
            progress = st.progress(0.0, text="Memulai...")
            try:
                from exam_generator.pipeline import run_pipeline

                def _on_progress(current, total, stage, message=None):
                    # Extraction drives the first 30% of the bar, variations the rest.
                    if stage == "extract":
                        frac = 0.3 * (current / max(total, 1))
                    else:
                        frac = 0.3 + 0.7 * (current / max(total, 1))
                    progress.progress(min(max(frac, 0.0), 1.0), text=message or "")
                    status.write(message or "")

                run_pipeline(
                    pdf_path=PDF_PATH,
                    output_docx=OUTPUT_PATH,
                    custom_instruction=custom_instruction,
                    progress_callback=_on_progress,
                )
                progress.progress(1.0, text="✅ Selesai!")
                status.update(label="✅ Pemrosesan Selesai!", state="complete")
            except Exception as e:
                status.update(label="❌ Terjadi kesalahan.", state="error")
                st.error(str(e))

        _render_download_and_preview()
