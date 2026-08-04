import streamlit as st
import subprocess
import os

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
            result = subprocess.run(
                ["python", "-m", "src.exam_generator.pipeline"], 
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                status.update(label="✅ Processing complete!", state="complete")
                output_path = "data/outputs/final_pipeline_result.docx"
                if os.path.exists(output_path):
                    with open(output_path, "rb") as file:
                        st.download_button(
                            label="⬇️ Download Final Word Document",
                            data=file,
                            file_name="Bank_Soal_Variasi.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True
                        )
            else:
                status.update(label="❌ Error occurred.", state="error")
                st.error(result.stderr)
