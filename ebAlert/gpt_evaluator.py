import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPEN_API_KEY"))

MODEL = "gpt-4o-mini"  # oder "gpt-3.5-turbo"

SYSTEM_PROMPT = """
Du bist ein professioneller Reseller.
Bewerte Kleinanzeigen ausschließlich objektiv und realistisch.
Antworte IMMER im gültigen JSON-Format.
"""

def evaluate_listing(title: str, description: str, price: float, market_price: float):
    user_prompt = f"""
Titel: {title}
Beschreibung: {description}
Angebotspreis: {price} EUR
Marktpreis (real verkauft): {market_price} EUR

Bewerte die Anzeige.

Gib zurück:
- condition: neu | sehr gut | gebraucht | defekt
- negotiability: hoch | mittel | niedrig
- expected_margin: erwarteter Gewinn in EUR
- score: 0-100 (Gewinn + Risiko kombiniert)

Antwort ausschließlich als JSON:
"""

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
    )

    try:
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print("GPT parsing error:", e)
        return None
