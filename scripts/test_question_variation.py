import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def main():
    # The JSON we extracted from the Vision API
    original_question = {
        "id": "25MATBLGBRLM01SU-000000-0246",
        "hierarchy": {
            "Elemen": "Bilangan",
            "Subelemen": "Bilangan Real",
            "Indikator": "Menyederhanakan bentuk bilangan berpangkat bulat atau pecahan."
        },
        "question_text": "Bentuk sederhana dari 3^(2/3) x 8^(3/2) / 2^(5/2) x 9^(5/6) adalah ....",
        "type": "Pilihan Ganda",
        "options": ["1/42", "2/3", "4/3", "6", "12"]
    }

    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    prompt = f"""You are an expert Indonesian high school math teacher. Given the following exam question in JSON format:
{json.dumps(original_question, indent=2, ensure_ascii=False)}

Generate two variations of this question: one 'easier' and one 'harder'. 
- The 'easier' version should use simpler numbers or more direct steps.
- The 'harder' version should use more complex numbers, nested fractions, or require more steps.
- Keep the same mathematical topic and hierarchy.
- Return ONLY a valid JSON object with exactly two keys: 'easier' and 'harder'. 
- Each variation must have 'question_text' and 'options' (a list of 5 strings). Do not include markdown formatting or explanations."""

    print("Sending question to Groq Text API for variation...")
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
        )
        
        response_text = chat_completion.choices[0].message.content
        print("\n--- AI RESPONSE ---")
        print(response_text)
        
        # Parse JSON using regex to ignore any stray text
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            print("\n✅ Successfully generated variations!")
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        else:
            print("\n⚠️ No JSON found in the response.")

    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
