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
    
    if st.button(" Buat Variasi", type="primary", use_container_width=True):
        with st.status("Sedang memproses PDF...", expanded=True) as status:
            st.write("Menjalankan AI pipeline...")
            try:
                from exam_generator.pipeline import run_pipeline
                output_path = "data/outputs/final_pipeline_result.docx"
                run_pipeline(
                    pdf_path="data/inputs/uploaded_exam.pdf",
                    output_docx=output_path,
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
            except Exception as e:
                status.update(label="❌ Terjadi kesalahan.", state="error")
                st.error(str(e))
