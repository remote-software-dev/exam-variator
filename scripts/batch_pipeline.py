import os
import json
import base64
import re
import subprocess
import time
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_question(client, image_path):
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are an expert at extracting exam questions. Return ONLY a valid JSON object with keys: 'id', 'question_text', 'options' (list of 5 strings). You MUST use LaTeX math notation (e.g., $\\frac{a}{b}$, $x^2$) for all formulas. Use double quotes."},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract the question from this image as JSON."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(image_path)}"}}
            ]}
        ],
        model="qwen/qwen3.6-27b",
        temperature=0.1,
    )
    raw_response = chat_completion.choices[0].message.content
    match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
    if not match: match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
    if match:
        try: return json.loads(match.group(1).replace("'", '"'))
        except: return None
    return None

def generate_variations(client, original_q):
    prompt = f"""Given this question: {json.dumps(original_q)}
    Generate 'easier' and 'harder' variations. Keep the same topic. 
    You MUST use LaTeX math notation. Return ONLY a JSON object with keys 'easier' and 'harder', each containing 'question_text' and 'options' (list of 5 strings). Use double quotes."""
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.7,
    )
    raw_response = chat_completion.choices[0].message.content
    match = re.search(r'```json\s*(\{.*\})\s*```', raw_response, re.DOTALL)
    if not match: match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
    if match:
        try: return json.loads(match.group(1).replace("'", '"'))
        except: return None
    return None

def export_batch_to_docx(all_questions, output_path):
    print("\n  [Final Step] Compiling professional DOCX via Pandoc...")
    md_content = "# Bank Soal & Variasi Matematika\n\n"
    
    for idx, data in enumerate(all_questions, 1):
        md_content += f"## Soal {idx} (ID: {data['original'].get('id', 'Unknown')})\n\n{data['original']['question_text']}\n\n"
        for i, opt in enumerate(data['original']['options']):
            md_content += f"{chr(65+i)}. {opt}\n"
        
        for variant in ['easier', 'harder']:
            if variant in data.get('variations', {}):
                md_content += f"\n---\n\n### Variasi Lebih {'Mudah' if variant == 'easier' else 'Sulit'}\n\n"
                md_content += f"{data['variations'][variant]['question_text']}\n\n"
                for i, opt in enumerate(data['variations'][variant]['options']):
                    md_content += f"{chr(65+i)}. {opt}\n"
        md_content += "\n\n---\n\n"

    md_path = output_path.replace('.docx', '.md')
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    subprocess.run(["pandoc", md_path, "-o", output_path, "--mathml", "-f", "markdown", "-t", "docx"], check=True)
    print(f"✅ Success! Batch output saved to: {output_path}")

def main():
    print("🚀 Starting Batch Exam Generator Pipeline...\n")
    pages_dir = "../data/outputs/pages"
    output_docx = "../data/outputs/batch_pipeline_result.docx"
    
    if not os.path.exists(pages_dir):
        print("❌ Error: Run 'python render_pages.py' first.")
        return

    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    all_questions = []
    
    png_files = sorted([f for f in os.listdir(pages_dir) if f.endswith('.png')])
    print(f"Found {len(png_files)} pages to process.\n")

    for filename in png_files:
        image_path = os.path.join(pages_dir, filename)
        print(f"📄 Processing {filename}...")
        
        try:
            original_q = extract_question(client, image_path)
            if not original_q:
                print(f"  ⚠️ Skipped {filename} (No question extracted).")
                continue
                
            variations = generate_variations(client, original_q)
            all_questions.append({"original": original_q, "variations": variations or {}})
            print(f"  ✅ Processed: {original_q.get('id', 'Unknown ID')}")
            
            # Small delay to be polite to the API rate limits
            time.sleep(1) 
        except Exception as e:
            print(f"  ❌ Error processing {filename}: {e}")

    if all_questions:
        os.makedirs(os.path.dirname(output_docx), exist_ok=True)
        export_batch_to_docx(all_questions, output_docx)
    else:
        print("❌ No questions were successfully processed.")

if __name__ == "__main__":
    main()
