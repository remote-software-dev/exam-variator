import os
import re
import base64
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def main():
    image_path = "data/outputs/pages/page_02.png"
    
    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found.")
        return

    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    base64_image = encode_image(image_path)

    print("Sending image to Groq Vision API...")
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at extracting exam questions from images. You must output ONLY valid JSON, no markdown formatting, no explanations."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the question from this image. Return ONLY a valid JSON object with these exact keys: 'id', 'hierarchy' (object with Elemen, Subelemen, Kompetensi, Indikator), 'question_text', 'type', and 'options' (a list of strings)."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                            },
                        },
                    ],
                }
            ],
            model="qwen/qwen3.6-27b",
            temperature=0.1,
        )
        
        response_text = chat_completion.choices[0].message.content
        print("\n--- AI RESPONSE ---")
        print(response_text)
        
        try:
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                print("\n✅ Successfully parsed into structured JSON!")
                print(json.dumps(parsed, indent=2))
            else:
                print("\n⚠️ No JSON object found in the response.")
        except json.JSONDecodeError:
            print("\n⚠️ AI response was not valid JSON.")

    except Exception as e:
        print(f"\n❌ Error calling Groq API: {e}")

if __name__ == "__main__":
    main()
