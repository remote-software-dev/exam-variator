import os
import subprocess

def main():
    output_dir = "data/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    md_path = os.path.join(output_dir, "soal_variasi.md")
    docx_path = os.path.join(output_dir, "soal_variasi_professional.docx")

    # 1. Create Markdown content with LaTeX math notation
    md_content = """
# Bank Soal & Variasi Matematika
*SMA/MA/SMK - Tahun 2025*

## Soal Asli (ID: 25MATBLGBRLM01SU-000000-0246)

Bentuk sederhana dari $\\frac{3^{\\frac{2}{3}} \\times 8^{\\frac{3}{2}}}{2^{\\frac{5}{2}} \\times 9^{\\frac{5}{6}}}$ adalah ....

A. $\\frac{1}{42}$
B. $\\frac{2}{3}$
C. $\\frac{4}{3}$
D. $6$
E. $12$

---

## Variasi Lebih Mudah

Bentuk sederhana dari $2^3 \\times 4^2 / 8^1$ adalah ....

A. $2$
B. $4$
C. $8$
D. $16$
E. $32$

---

## Variasi Lebih Sulit

Bentuk sederhana dari $\\frac{27^{\\frac{4}{3}} \\times 16^{\\frac{3}{4}}}{8^{\\frac{5}{3}} \\times 9^{\\frac{3}{2}}}$ adalah ....

A. $\\frac{1}{9}$
B. $\\frac{2}{9}$
C. $\\frac{4}{9}$
D. $\\frac{8}{9}$
E. $1$
"""

    # Save Markdown file
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✅ Created Markdown file: {md_path}")

    # 2. Convert Markdown to DOCX using Pandoc
    # --mathml ensures equations are converted to native Word equation editor format
    print("Converting to DOCX using Pandoc...")
    try:
        subprocess.run([
            "pandoc", md_path, 
            "-o", docx_path, 
            "--mathml", 
            "-f", "markdown", 
            "-t", "docx"
        ], check=True)
        print(f"✅ Successfully generated professional Word document: {docx_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running Pandoc: {e}")
        print("Make sure Pandoc is installed: sudo apt install pandoc")

if __name__ == "__main__":
    main()
