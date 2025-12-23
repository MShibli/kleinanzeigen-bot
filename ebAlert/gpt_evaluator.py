import os
import re
import json
from openai import OpenAI
from ebAlert.core.config import settings

client = OpenAI(api_key=settings.OPEN_API_KEY)

MODEL = "gpt-4.1-mini"
MODEL_SEARCH_QUERY = "gpt-4.1-mini"

SYSTEM_PROMPT = """
Du bist ein Experten-Reseller für Elektronik. Deine Aufgabe: Bewerten von Ankauf-Deals basierend auf Gewinnmarge, Risiko und Marktgängigkeit.
Eingabe: JSON mit Anzeige (Titel, Beschreibung, Preis und eBay-Median).

Bewertungs-Logik:
1. Marge % = ((eBay-Median * 0.9) - Angebotspreis) / eBay-Median. (0.9 berücksichtigt ca. 10% Gebühren/Versand).
2. Bonus:
   - "VB" (Verhandlungsbasis) im Preis: +10 Punkte auf Verhandelbarkeit.
   - OVP/Rechnung vorhanden: +10 Punkte auf Score.

Score-Skalierung (Gewichtung: 70% Marge, 30% Zustand/Risiko):
- 80-100 (Hervorragend): Marge > 20% UND Zustand min. 'sehr gut'.
- 50-79 (Gut): Marge 10-20% ODER hohe Verhandelbarkeit.
- 20-49 (Riskant): Marge < 10% ODER Zustand 'gebraucht'.
- 0-19 (Kein Deal): Marge negativ ODER Zustand 'defekt'.

Ausgabe: AUSSCHLIESSLICH ein valides JSON-Array. Kein Markdown, kein Text.
Format:
[{
  "id": "string",
  "condition": "neu" | "sehr gut" | "gebraucht" | "defekt",
  "negotiability": "hoch" | "mittel" | "niedrig",
  "expected_margin_eur": number,
  "score": 0-100,
  "reason": "Kurzer Grund für Score"
}]
"""

def generate_search_queries_batch(items: list):
    """Wandelt Titel in präzise eBay-Suchbegriffe um."""
    prompt = "Extrahiere für jede Anzeige den präzisesten Suchbegriff für eBay (Modellname, Kapazität, etc.). Keine Farben oder Zustandsbeschreibungen. Antworte als JSON-Objekt: {'queries': [{'id': '...', 'query': '...'}]}"
    input_data = [{"id": str(i.get('id')), "title": i.get('title')} for i in items]
    
    try:
        response = client.chat.completions.create(
            model=MODEL_SEARCH_QUERY,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Du bist ein Daten-Parser. Extrahiere nur Markennamen und Modell."},
                {"role": "user", "content": f"{prompt}\nAnzeigen: {json.dumps(input_data)}"}
            ]
        )
        print("GPT search_queries_batch Result:", json.loads(response.choices[0].message.content).get('queries', []))
        return json.loads(response.choices[0].message.content).get('queries', [])
    except Exception as e:
        print("GPT search_queries_batch Error:", e)
        return []

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
        print("GPT evaluate_listings_batch Result:", content)
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
