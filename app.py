import streamlit as st
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

st.set_page_config(page_title="Generator Variasi Soal", layout="centered")
st.title("🎓 Generator Variasi Soal")
st.markdown("Unggah PDF soal ujian untuk mengekstrak soal secara otomatis, membuat variasi soal yang lebih mudah atau lebih sulit, dan mengunduh dokumen hasil dalam bentuk Word.")

uploaded_file = st.file_uploader("Pilih file PDF", type="pdf")

if uploaded_file is not None:
    with open("data/inputs/uploaded_exam.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())

    custom_instruction = st.text_area(
        "Instruksi Tambahan (Opsional)",
        placeholder="Contoh: Buat penyelesaian dengan konsep dasar, atau jelaskan cara cepat/trik mengerjakan soal ini...",
    )

    if st.button(" Buat Variasi", type="primary", use_container_width=True):
        with st.status("Sedang memproses PDF...", expanded=True) as status:
            st.write("Menjalankan AI pipeline...")
            try:
                from exam_generator.pipeline import run_pipeline
                output_path = "data/outputs/final_pipeline_result.docx"
                run_pipeline(
                    pdf_path="data/inputs/uploaded_exam.pdf",
                    output_docx=output_path,
                    custom_instruction=custom_instruction,
                )
                status.update(label="✅ Pemrosesan Selesai!", state="complete")
                if os.path.exists(output_path):
                    with open(output_path, "rb") as file:
                        st.download_button(
                            label="⬇️ Download Hasil Akhir Dokumen Word",
                            data=file,
                            file_name="Bank_Soal_Variasi.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True
                        )

                # Live preview of the results (st.markdown renders $...$ LaTeX).
                results_json = output_path.rsplit(".", 1)[0] + ".json"
                if os.path.exists(results_json):
                    import json as _json
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
            except Exception as e:
                status.update(label="❌ Terjadi kesalahan.", state="error")
                st.error(str(e))
