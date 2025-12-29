import os
import re
import json
from openai import OpenAI
from ebAlert.core.config import settings

client = OpenAI(api_key=settings.OPEN_API_KEY)

MODEL = "gpt-4.1-mini"
MODEL_SEARCH_QUERY = "gpt-4.1-mini"

SYSTEM_PROMPT_SCORING = """
ROLE: Professional Electronics Reseller.
TASK:
Classify each listing. Do NOT calculate prices or margins.

RULES:
- Output JSON only
- No prose, no markdown
- One object per input item

CLASSIFICATION RULES:
1) BUNDLE: 
true only if: 
listing has ≥2 different hardware types from {CPU, GPU, RAM, Mainboard}.
listing for a complete PC.

false if:
Multiple items of the same type (e.g., 2x RAM).
only 1 hardware type.

2) obsolete:
true ONLY if:
- RAM is DDR3 or older
- Intel CPU is < 8th Gen
- AMD CPU is < Ryzen 2000
- iPhone model < iPhone 11
- Samsung S < S22
- Samsung A < A55
- Other smartphones released before 2023

false if:
- RAM is DDR4 or DDR5
- CPU meets or exceeds the limits above
- Smartphone meets or exceeds the limits above

3) accessory_only: true if neither a hardware part nor a complete pc nor a smartphone.
4) liquidity: high | medium | low

OUTPUT FORMAT:
{
  "result": [
    {
      "id": "string",
      "bundle": boolean,
      "obsolete": boolean,
      "accessory_only": boolean,
      "liquidity": "high|medium|low"
    }
  ]
}
"""

SYSTEM_PROMPT_QUERY_SEARCH= """
Du bist ein Daten-Parser. Extrahiere nur Markennamen und Modell.
"""

# Sicherstellen, dass CACHE_DIR definiert ist (aus Umgebungsvariable oder lokal)
BASE_DIR = os.getenv("CACHE_DIR", os.path.expanduser("~"))
GPT_CACHE_FILE = os.path.join(BASE_DIR, "gpt_query_cache.json")

def load_gpt_cache():
    if os.path.exists(GPT_CACHE_FILE):
        try:
            with open(GPT_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("GPT load_gpt_cache Error:", e)
            return {}

    print("GPT load_gpt_cache Error: Keine Cachedatei gefunden!")
    return {}

def save_gpt_cache(cache):
    try:
        # Debug: Zeige wo gespeichert wird
        print(f"💾 Speichere GPT-Cache ({len(cache)} Einträge) in: {GPT_CACHE_FILE}")
        with open(GPT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=4)
    except Exception as e:
        print(f"❌ Fehler beim Speichern des Caches: {e}")

def generate_search_queries_batch(items: list):
    """Wandelt Titel in präzise eBay-Suchbegriffe um mit Caching."""
    if not items:
        return []

    gpt_cache = load_gpt_cache()
    results = []
    to_request_gpt = []

    for item in items:
        # Radikale Normalisierung für den Cache-Key
        raw_title = item.get('title', '')
        # Entferne alle doppelten Leerzeichen und trimme
        clean_key = " ".join(raw_title.split()).lower()
        item_id = str(item.get('id'))
        
        if clean_key in gpt_cache:
            print(f"✅ Cache-Hit: {clean_key}")
            results.append({'id': item_id, 'query': gpt_cache[clean_key]})
        else:
            to_request_gpt.append(item)

    if not to_request_gpt:
        return results

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
        new_entries = 0
        for q_data in gpt_results:
            q_id = str(q_data.get('id')) # Sicherstellen, dass ID ein String ist
            q_text = q_data.get('query')

            if not q_text: continue
            
            # Suche das Item anhand der ID
            orig_item = next((x for x in to_request_gpt if str(x.get('id')) == q_id), None)
            
            if orig_item:
                # Nutze den exakt gleichen clean_key wie oben!
                clean_key = " ".join(orig_item.get('title', '').split()).lower()
                gpt_cache[clean_key] = q_text
                new_entries += 1
            
            results.append({'id': q_id, 'query': q_text})

        if new_entries > 0:
            save_gpt_cache(gpt_cache)
            
        return results

    except Exception as e:
        print("GPT search_queries_batch Error:", e)
        # Im Fehlerfall geben wir zumindest die Cache-Ergebnisse zurück
        return results

def evaluate_listings_batch(listings: list, chunk_size: int = 12):
    """
    Unterteilt die Liste der Artikel in kleinere Blöcke (Chunks),
    um die Genauigkeit der KI zu erhöhen und Fehler zu vermeiden.
    """
    if not listings:
        return []

    all_results = []

    # Unterteilen der Gesamtliste in Teil-Listen (z.B. jeweils 12 Artikel)
    for i in range(0, len(listings), chunk_size):
        current_chunk = listings[i:i + chunk_size]
        
        try:
            print(f"--- 🧠 GPT Evaluation: Verarbeite Batch {i // chunk_size + 1} ({len(current_chunk)} Items) ---")
            
            response = client.chat.completions.create(
                model=MODEL,
                temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_SCORING},
                    {"role": "user", "content": json.dumps(current_chunk)}
                ]
            )

            content = json.loads(response.choices[0].message.content)
            batch_results = content.get("result", [])
            
            # Die Ergebnisse des aktuellen Chunks an die Gesamtliste anhängen
            all_results.extend(batch_results)

        except Exception as e:
            print(f"❌ GPT Batch Error bei Index {i}: {e}")
            # Wir machen trotz Fehlers beim nächsten Chunk weiter, 
            # damit nicht alle Ergebnisse verloren gehen.
            continue

    return all_results

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
