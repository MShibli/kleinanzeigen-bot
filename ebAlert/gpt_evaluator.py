import os
import re
import json
from openai import OpenAI
from ebAlert.core.config import settings

client = OpenAI(api_key=settings.OPEN_API_KEY)

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """
Du bist ein professioneller Reseller. Dir wird eine Liste von Verkaufsanzeigen im JSON-Format übergeben.
Bewerte jede Anzeige einzeln.

Antworte AUSSCHLIESSLICH mit einem validen JSON-Array von Objekten.
Jedes Objekt MUSS die 'id' der Anzeige enthalten, um sie zuzuordnen.

Format pro Objekt:
{
  "id": "string",
  "condition": "neu" | "sehr gut" | "gebraucht" | "defekt",
  "negotiability": "hoch" | "mittel" | "niedrig",
  "expected_margin_eur": number,
  "score": 0-100
}

Berechne intern:
- realistischer eBay.de Verkaufspreis anhand historischer Daten bei eBay.de
- eBay-Gebühren pauschal 6,5%
- Versandkosten pauschal 6 €

Der Score basiert PRIMÄR auf expected_margin_eur:
- >100 € → Score 80–100
- 20–50 € → Score 50–79
- 5–20 € → Score 20–49
- <5 € → Score 0–19

KEIN Text, KEIN Markdown, nur das Array.
"""

def evaluate_listings_batch(listings: list):
    """
    listings: Liste von dicts mit {id, title, description, price}
    """
    if not listings:
        return []

    user_prompt = json.dumps(listings, ensure_ascii=False)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.1,
            response_format={"type": "json_object"},  # Erzwingt JSON-Mode
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Bewerte diese Anzeigen: {user_prompt}"}
            ]
        )

        content = response.choices[0].message.content
        # Wir erwarten ein Objekt mit einem Key "evaluations" oder direkt ein Array. 
        # Da wir JSON-Mode nutzen, packen wir es sicherheitshalber in ein Root-Objekt im Prompt.
        parsed = json.loads(content)
        
        # Falls GPT das Array in einen Key packt (passiert oft bei json_object mode)
        if isinstance(parsed, dict):
            for key in parsed:
                if isinstance(parsed[key], list):
                    return parsed[key]
        
        return parsed if isinstance(parsed, list) else []

    except Exception as e:
        print("GPT Batch Error:", e)
        return []

def extract_json(text: str):
    # Hilfsfunktion bleibt für Notfälle, wird aber durch response_format seltener gebraucht
    try:
        return json.loads(text)
    except:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try: return json.loads(match.group())
            except: return None
    return None
