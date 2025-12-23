import os
import re
import json
from openai import OpenAI
from ebAlert.core.config import settings

client = OpenAI(api_key=settings.OPEN_API_KEY)

MODEL = "gpt-4.1-mini"
MODEL_SEARCH_QUERY = "gpt-4.1-mini"

SYSTEM_PROMPT_SCORING = """
Du bist ein Experten-Reseller für Elektronik. Deine Aufgabe: Bewerten von Ankauf-Deals basierend auf Gewinnmarge, Risiko und Marktgängigkeit.
Eingabe: JSON mit Anzeige (Titel, Beschreibung, Preis und eBay-Median).

Bewertungs-Logik:
Marge % = ((eBay-Median * 0.9) - Angebotspreis) / eBay-Median. (0.9 berücksichtigt ca. 10% Gebühren/Versand).

Score-Skalierung:
- 80-100 (Hervorragend): Marge > 20%.
- 50-79 (Gut): Marge 10-20% ODER hohe Verhandelbarkeit.
- 20-49 (Riskant): Marge < 10%.
- 0-19 (Kein Deal): Marge negativ.

Antworte als JSON-Array von Objekten mit folgendem Format:
{
	"result": [
		"id": "string",
		"negotiability": "hoch" | "mittel" | "niedrig",
		"expected_margin_eur": number,
		"score": 0-100
  ]
}
"""

SYSTEM_PROMPT_QUERY_SEARCH= """
Du bist ein Daten-Parser. Extrahiere nur Markennamen und Modell.
"""

GPT_CACHE_FILE = os.path.join(CACHE_DIR, "gpt_query_cache.json")

def load_gpt_cache():
    if os.path.exists(GPT_CACHE_FILE):
        try:
            with open(GPT_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_gpt_cache(cache):
    with open(GPT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4)

def generate_search_queries_batch(items: list):
    """Wandelt Titel in präzise eBay-Suchbegriffe um mit Caching."""
    if not items:
        return []

    gpt_cache = load_gpt_cache()
    results = []
    to_request_gpt = []

    # 1. Schritt: Prüfen, was wir schon wissen
    for item in items:
        title = item.get('title', '').strip()
        item_id = str(item.get('id'))
        
        if title in gpt_cache:
            # Aus Cache nehmen
			print(f"✅ GPT-Cache Treffer: id: {item_id}, query: {gpt_cache[title]}")
            results.append({'id': item_id, 'query': gpt_cache[title]})
        else:
            # Für GPT-Anfrage vormerken
            to_request_gpt.append(item)

    # Wenn alles im Cache war, können wir hier schon aufhören
    if not to_request_gpt:
        print(f"✅ GPT-Cache: Alle {len(items)} Suchbegriffe aus Cache geladen.")
        return results

    # 2. Schritt: Nur die neuen Items an GPT senden
    print(f"🤖 GPT-Anfrage für {len(to_request_gpt)} neue Titel...")
    prompt = "Extrahiere für jede Anzeige den präzisesten Suchbegriff für eBay (Modellname, Kapazität, etc.). Keine Farben oder Zustandsbeschreibungen. Antworte als JSON-Objekt: {'queries': [{'id': '...', 'query': '...'}]}"
    input_data = [{"id": str(i.get('id')), "title": i.get('title')} for i in to_request_gpt]
    
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
        
        gpt_results = json.loads(response.choices[0].message.content).get('queries', [])
        
        # 3. Schritt: Neue Ergebnisse cachen und zur Liste hinzufügen
        for q_data in gpt_results:
            q_id = q_data['id']
            q_text = q_data['query']

			if not q_text:
				continue
			
            # Finde den originalen Titel für den Cache-Key
            orig_item = next((x for x in to_request_gpt if str(x['id']) == q_id), None)
            if orig_item:
                gpt_cache[orig_item['title'].strip()] = q_text
            
            results.append(q_data)

        # Cache speichern
        save_gpt_cache(gpt_cache)
        return results

    except Exception as e:
        print("GPT search_queries_batch Error:", e)
        # Im Fehlerfall geben wir zumindest die Cache-Ergebnisse zurück
        return results

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
                {"role": "system", "content": SYSTEM_PROMPT_SCORING},
                {"role": "user", "content": f"Bewerte diese Anzeigen: {user_prompt}"}
            ]
        )

        content = json.loads(response.choices[0].message.content)
        return content if isinstance(content, list) else content.get('result', [])

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
