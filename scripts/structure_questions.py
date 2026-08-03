import fitz
import json
import re
import os

def main():
    pdf_path = "data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf"
    output_dir = "data/outputs"
    output_path = os.path.join(output_dir, "structured_questions.json")
    os.makedirs(output_dir, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    questions = []
    current_question = None
    
    # FIXED Regex: 25 + 14 alphanumeric chars + 6 digits + 4 digits
    qid_regex = re.compile(r'25[A-Z0-9]{14}-\d{6}-\d{4}')
    
    for page_num in range(doc.page_count):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        
        for block in blocks:
            if block["type"] == 0: # Text block
                # Extract all text from the block, joining spans
                text = "".join(span["text"] for line in block["lines"] for span in line["spans"])
                
                qid_match = qid_regex.search(text)
                if qid_match:
                    # Save the previous question if it exists
                    if current_question:
                        questions.append(current_question)
                    
                    # Start a new question
                    current_question = {
                        "id": qid_match.group(0),
                        "text": text.replace(qid_match.group(0), "").strip(),
                        "images": [],
                        "options": []
                    }
                elif current_question:
                    # Append text to the current question
                    current_question["text"] += " " + text.strip()
                    
            elif block["type"] == 1 and current_question: # Image block
                img_data = block["image"]
                img_ext = block["ext"]
                img_filename = f"img_{current_question['id']}_{len(current_question['images'])}.{img_ext}"
                img_path = os.path.join(output_dir, img_filename)
                
                with open(img_path, "wb") as f:
                    f.write(img_data)
                current_question["images"].append(img_filename)
                
    # Don't forget the last question!
    if current_question:
        questions.append(current_question)
        
    doc.close()
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Successfully structured {len(questions)} questions into {output_path}")

if __name__ == "__main__":
    main()
