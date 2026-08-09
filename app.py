import json as _json
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

st.set_page_config(page_title="Generator Variasi Soal", layout="centered")
st.title("🎓 Generator Variasi Soal")
st.markdown("Unggah PDF soal ujian untuk mengekstrak semua soal secara otomatis, membuat variasi soal yang lebih mudah atau lebih sulit, dan mengunduh dokumen hasil dalam bentuk Word.")

BATCH_SIZE = 5
PDF_PATH = "data/inputs/uploaded_exam.pdf"
OUTPUT_PATH = "data/outputs/final_pipeline_result.docx"


@st.dialog("Lanjutkan Pemrosesan?")
def _continue_dialog(processed, total, remaining):
    st.write(f"✅ **{processed} dari {total}** soal berhasil diproses.")
    st.write(f"Masih ada **{remaining}** soal lagi. Lanjutkan memproses 5 soal berikutnya?")
    col1, col2 = st.columns(2)
    if col1.button("Lanjutkan ➡️", use_container_width=True):
        st.session_state["_await_confirmation"] = False
        st.rerun()
    if col2.button("Selesai (pakai hasil sejauh ini)", use_container_width=True):
        st.session_state["_finish_early"] = True
        st.rerun()


def _process_next_batch():
    """Generate variations for the next batch and append the results."""
    from exam_generator.pipeline import generate_variation_batch

    questions = st.session_state["_questions"]
    start = st.session_state["_next_index"]
    batch = generate_variation_batch(
        questions, start, BATCH_SIZE, custom_instruction=st.session_state["_instruction"]
    )
    st.session_state["_results"].extend(batch)
    st.session_state["_next_index"] += len(batch)


def _export_and_finish():
    """Export the collected results to DOCX + JSON and mark the flow as done."""
    from exam_generator.docx_exporter import export_docx

    results = st.session_state["_results"]
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    export_docx(results, OUTPUT_PATH)

    results_json = OUTPUT_PATH.rsplit(".", 1)[0] + ".json"
    with open(results_json, "w", encoding="utf-8") as f:
        _json.dump({"questions": results}, f, ensure_ascii=False, indent=2)

    st.session_state["_flow_active"] = False
    st.session_state["_done"] = True


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
        st.markdown(f"**Soal Asli**\n\n{original.get('question_text', '')}")
        options = original.get("options") or []
        if options:
            st.markdown("**Opsi Jawaban:**")
            for i, opt in enumerate(options):
                st.markdown(f"- **{chr(65 + i)}.** {opt}")
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


uploaded_file = st.file_uploader("Pilih file PDF", type="pdf")

if uploaded_file is not None:
    with open(PDF_PATH, "wb") as f:
        f.write(uploaded_file.getbuffer())

    custom_instruction = st.text_area(
        "Instruksi Tambahan (Opsional)",
        placeholder="Contoh: Buat penyelesaian dengan konsep dasar, atau jelaskan cara cepat/trik mengerjakan soal ini...",
    )

    if st.button("🚀 Buat Variasi", type="primary", use_container_width=True):
        with st.status("Sedang memproses PDF...", expanded=True) as status:
            st.write("Mengekstrak semua soal dari PDF...")
            try:
                from exam_generator.pipeline import extract_all_questions_from_pdf
                questions, skipped_pages = extract_all_questions_from_pdf(
                    pdf_path=PDF_PATH,
                    custom_instruction=custom_instruction,
                )
                if not questions:
                    raise RuntimeError("Tidak ada soal yang berhasil diekstrak dari PDF.")
                st.session_state["_questions"] = questions
                st.session_state["_results"] = []
                st.session_state["_next_index"] = 0
                st.session_state["_instruction"] = custom_instruction
                st.session_state["_total"] = len(questions)
                st.session_state["_flow_active"] = True
                st.session_state["_await_confirmation"] = False
                st.session_state["_finish_early"] = False
                st.session_state["_done"] = False
                status.update(label=f"✅ Diekstrak {len(questions)} soal.", state="complete")
                if skipped_pages:
                    st.warning(f"⚠ Halaman yang dilewati: {skipped_pages}")
            except Exception as e:
                status.update(label="❌ Terjadi kesalahan.", state="error")
                st.error(str(e))
        st.rerun()

    if st.session_state.get("_flow_active"):
        total = st.session_state["_total"]
        processed = len(st.session_state["_results"])

        if processed < total:
            if st.session_state.get("_await_confirmation"):
                if st.session_state.get("_finish_early"):
                    _export_and_finish()
                else:
                    _continue_dialog(processed, total, total - processed)
            else:
                start = st.session_state["_next_index"] + 1
                end = min(st.session_state["_next_index"] + BATCH_SIZE, total)
                with st.status(f"⏳ Membuat variasi soal {start}–{end} dari {total}...", expanded=True):
                    _process_next_batch()
                processed = len(st.session_state["_results"])
                if processed >= total:
                    _export_and_finish()
                else:
                    st.session_state["_await_confirmation"] = True
                st.rerun()

    if st.session_state.get("_done"):
        st.success(f"✅ Semua soal selesai diproses!")
        if os.path.exists(OUTPUT_PATH):
            with open(OUTPUT_PATH, "rb") as file:
                st.download_button(
                    label="⬇️ Download Hasil Akhir Dokumen Word",
                    data=file,
                    file_name="Bank_Soal_Variasi.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )
        _render_preview()
