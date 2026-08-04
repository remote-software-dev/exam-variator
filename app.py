import streamlit as st
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

st.set_page_config(page_title="Generator Variasi Soal", layout="centered")
st.title("🎓 Generator Variasi Soal")
st.markdown("Upload a scanned PDF exam to automatically extract questions, generate easier/harder variations, and download a professional Word document.")

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    with open("data/inputs/uploaded_exam.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    if st.button(" Generate Variations", type="primary", use_container_width=True):
        with st.status("Processing PDF...", expanded=True) as status:
            st.write("Running AI pipeline...")
            try:
                from exam_generator.pipeline import run_pipeline
                output_path = "data/outputs/final_pipeline_result.docx"
                run_pipeline(
                    pdf_path="data/inputs/uploaded_exam.pdf",
                    output_docx=output_path,
                )
                status.update(label="✅ Processing complete!", state="complete")
                if os.path.exists(output_path):
                    with open(output_path, "rb") as file:
                        st.download_button(
                            label="⬇️ Download Final Word Document",
                            data=file,
                            file_name="Bank_Soal_Variasi.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True
                        )
            except Exception as e:
                status.update(label="❌ Error occurred.", state="error")
                st.error(str(e))
