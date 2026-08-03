import os
import sys
import json
import base64
import re
import subprocess
from groq import Groq
from dotenv import load_dotenv

# Add the project root to the path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

load_dotenv()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_question_from_image(image_path):
    print("  [1/4] Extracting question from image using Groq Vision...")
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    base64_image = encode_image(image_path)
    
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are an expert at extracting exam questions. Return ONLY a valid JSON object with keys: 'id', 'question_text', 'options' (list of strings). Use LaTeX math notation (e.g., $\\frac{a}{b}$, $x^2$) for formulas."},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract the first question from this image as JSON."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]}
        ],
        model="llama-3.2-11b-vision-preview",
        temperature=0.1,
    )
    
    match = re.search(r'\{.*\}', chat_completion.choices[0].message.content, re.DOTALL)
    return json.loads(match.group(0)) if match else None

def generate_variations(original_q):
    print("  [2/4] Generating easier and harder variations using Groq Text...")
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    prompt = f"""Given this question: {json.dumps(original_q)}
    Generate 'easier' and 'harder' variations. Keep the same topic. Use LaTeX math notation. 
    Return ONLY a JSON object with keys 'easier' and 'harder', each containing 'question_text' and 'options'."""
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.7,
    )
    
    match = re.search(r'\{.*\}', chat_completion.choices[0].message.content, re.DOTALL)
    return json.loads(match.group(0)) if match else None

def generate_docx(data, output_path):
    print("  [3/4] Creating Markdown file with LaTeX math...")
    md_content = f"# Bank Soal & Variasi Matematika\n\n"
    md_content += f"## Soal Asli (ID: {data['original']['id']})\n\n{data['original']['question_text']}\n\n"
    for i, opt in enumerate(data['original']['options']):
        md_content += f"{chr(65+i)}. {opt}\n"
    
    for variant in ['easier', 'harder']:
        if variant in data['variations']:
            md_content += f"\n---\n\n## Variasi Lebih {'Mudah' if variant == 'easier' else 'Sulit'}\n\n"
            md_content += f"{data['variations'][variant]['question_text']}\n\n"
            for i, opt in enumerate(data['variations'][variant]['options']):
                md_content += f"{chr(65+i)}. {opt}\n"

    md_path = output_path.replace('.docx', '.md')
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print("  [4/4] Converting to professional DOCX using Pandoc...")
    subprocess.run(["pandoc", md_path, "-o", output_path, "--mathml", "-f", "markdown", "-t", "docx"], check=True)
    print(f"✅ Success! Output saved to: {output_path}")

def main():
    print("🚀 Starting End-to-End Exam Generator Pipeline...\n")
    
    # Paths
    pdf_path = "data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf"
    page_png = "data/outputs/pages/page_02.png" # Using our known good test page
    output_docx = "data/outputs/final_pipeline_test.docx"
    
    if not os.path.exists(page_png):
        print("❌ Error: Run render_pages.py first to generate PNGs.")
        return

    # 1. Extract
    original_q = extract_question_from_image(page_png)
    if not original_q:
        print("❌ Failed to extract question.")
        return
    print(f"  ✅ Extracted: {original_q.get('id', 'Unknown ID')}")

    # 2. Vary
    variations = generate_variations(original_q)
    if not variations:
        print("❌ Failed to generate variations.")
        return
    print("  ✅ Variations generated.")

    # 3. Export
    os.makedirs(os.path.dirname(output_docx), exist_ok=True)
    generate_docx({
        "original": original_q,
        "variations": variations
    }, output_docx)

if __name__ == "__main__":
    main()
