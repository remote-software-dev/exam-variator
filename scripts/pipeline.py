import os
import sys
import json
import base64
import re
import subprocess
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_question(image_path):
    print("  [1/3] Extracting question via Groq Vision (Qwen 3.6 27B)...")
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are an expert at extracting exam questions. Return ONLY a valid JSON object with keys: 'id', 'question_text', 'options' (list of 5 strings). You MUST use LaTeX math notation (e.g., $\\frac{a}{b}$, $x^2$) for all formulas. Use double quotes for all JSON keys and string values."},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract the first question from this image as JSON."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(image_path)}"}}
            ]}
        ],
        model="qwen/qwen3.6-27b",
        temperature=0.1,
    )
    
    raw_response = chat_completion.choices[0].message.content
    match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
    if not match:
        match = re.search(r'(\{.*\})', raw_response, re.DOTALL) # Greedy match
        
    if match:
        try:
            clean_json = match.group(1).replace("'", '"')
            return json.loads(clean_json)
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON Decode Error: {e}")
            return None
    return None

def generate_variations(original_q):
    print("  [2/3] Generating variations via Groq Text...")
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    prompt = f"""Given this question: {json.dumps(original_q)}
    Generate 'easier' and 'harder' variations. Keep the same topic. 
    You MUST use LaTeX math notation (e.g., $\\frac{{a}}{{b}}$, $x^2$) for all formulas.
    Return ONLY a valid JSON object with keys 'easier' and 'harder', each containing 'question_text' and 'options' (list of 5 strings). Use double quotes."""
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.7,
    )
    
    raw_response = chat_completion.choices[0].message.content
    
    # Use GREEDY regex to capture the entire nested JSON object
    match = re.search(r'```json\s*(\{.*\})\s*```', raw_response, re.DOTALL)
    if not match:
        match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
        
    if match:
        try:
            clean_json = match.group(1).replace("'", '"')
            return json.loads(clean_json)
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON Decode Error in variations: {e}")
            print(f"  [DEBUG] Raw Variations Response:\n{raw_response}\n")
            return None
            
    print(f"  [DEBUG] No JSON found in Variations Response:\n{raw_response}\n")
    return None

def export_to_docx(data, output_path):
    print("  [3/3] Exporting to professional DOCX via Pandoc...")
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
        
    subprocess.run(["pandoc", md_path, "-o", output_path, "--mathml", "-f", "markdown", "-t", "docx"], check=True)
    print(f"✅ Success! Output saved to: {output_path}")

def main():
    print("🚀 Starting End-to-End Exam Generator Pipeline...\n")
    
    page_png = "../data/outputs/pages/page_02.png" 
    output_docx = "../data/outputs/final_pipeline_result.docx"
    
    if not os.path.exists(page_png):
        print("❌ Error: Run 'python render_pages.py' first.")
        return

    original_q = extract_question(page_png)
    if not original_q:
        print("❌ Failed to extract question.")
        return
    print(f"  ✅ Extracted: {original_q.get('id', 'Unknown ID')}")

    variations = generate_variations(original_q)
    if not variations:
        print("❌ Failed to generate variations.")
        return
    print("  ✅ Variations generated.")

    os.makedirs(os.path.dirname(output_docx), exist_ok=True)
    export_to_docx({"original": original_q, "variations": variations}, output_docx)

if __name__ == "__main__":
    main()
