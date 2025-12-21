import os
import re
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """
Du bist ein professioneller Reseller.
Antworte AUSSCHLIESSLICH mit gültigem JSON.
KEIN Text, KEINE Erklärungen, KEIN Markdown.
Wenn eine Bewertung nicht möglich ist, gib folgendes JSON zurück:

{
  "condition": "unbekannt",
  "negotiability": "niedrig",
  "expected_margin": 0,
  "score": 0
}
"""


def evaluate_listing(title: str, description: str, price: float):
    user_prompt = f"""
Titel: {title}
Beschreibung: {description}
Angebotspreis: {price} EUR

Bewerte die Anzeige.

Gib zurück:
- condition: neu | sehr gut | gebraucht | defekt
- negotiability: hoch | mittel | niedrig
- expected_margin: erwarteter Gewinn in EUR
- score: 0-100 (Gewinn + Risiko kombiniert)

Antwort ausschließlich als JSON:
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.1,
            max_tokens=300,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
        )

        content = response.choices[0].message.content
        print("GPT RAW RESPONSE:", content)

        parsed = extract_json(content)
        if not parsed:
            return {
                "condition": "unbekannt",
                "negotiability": "niedrig",
                "expected_margin": 0,
                "score": 0
            }

        return parsed

    except Exception as e:
        print("GPT parsing error:", e)
        return {
            "condition": "unbekannt",
            "negotiability": "niedrig",
            "expected_margin": 0,
            "score": 0
        }


def extract_json(text: str):
    try:
        return json.loads(text)
    except:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            return None

    return None
