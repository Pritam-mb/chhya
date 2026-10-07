import re
import os
import json
import datetime
from typing import Dict, Any, Optional

# Check if groq or openai is available
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


DEFAULT_POIS = [
    {"name": "Dadu's Residence (Middleton Row)", "aliases": ["home", "dadu's home", "house", "residence", "middleton row", "dadu"]},
    {"name": "Belle Vue Clinic", "aliases": ["clinic", "the clinic", "belle vue", "belle vue clinic", "doctor", "hospital", "dispensary"]},
    {"name": "Park Clinic", "aliases": ["park clinic", "gorky terrace clinic"]},
    {"name": "Flurys Tea Room", "aliases": ["flurys", "tea room", "bakery", "cafe", "park street tea room"]},
    {"name": "Oxford Bookstore", "aliases": ["oxford bookstore", "bookstore", "books", "oxford"]},
    {"name": "Camac Street Mall & Offices", "aliases": ["camac street", "camac square", "offices", "mall"]},
    {"name": "Russell Street Market & Pharmacy", "aliases": ["russell street", "pharmacy", "market", "chemist"]}
]


def offline_parse_request(text: str) -> Dict[str, Any]:
    """
    Deterministic rule-based & regex semantic extractor that runs 100% offline
    on the host machine without internet, satisfying P0-4 and acceptance checks.
    """
    text_lower = text.lower().strip()
    
    # 1. Depart time extraction
    depart_time = "15:00"  # default
    
    # Check for "noon", "12 pm", "morning", "afternoon", "evening"
    if re.search(r'\bnoon\b', text_lower) or "12 pm" in text_lower or "12pm" in text_lower:
        depart_time = "12:00"
    elif "morning" in text_lower or "9 am" in text_lower or "9am" in text_lower:
        depart_time = "09:00"
    elif "8 am" in text_lower or "8am" in text_lower:
        depart_time = "08:00"
    elif "10 am" in text_lower or "10am" in text_lower:
        depart_time = "10:00"
    elif "11 am" in text_lower or "11am" in text_lower:
        depart_time = "11:00"
    elif "1 pm" in text_lower or "1pm" in text_lower or "13:00" in text_lower:
        depart_time = "13:00"
    elif "2 pm" in text_lower or "2pm" in text_lower or "14:00" in text_lower:
        depart_time = "14:00"
    elif "3 pm" in text_lower or "3pm" in text_lower or "15:00" in text_lower or "around 3" in text_lower:
        depart_time = "15:00"
    elif "4 pm" in text_lower or "4pm" in text_lower or "16:00" in text_lower:
        depart_time = "16:00"
    elif "5 pm" in text_lower or "5pm" in text_lower or "17:00" in text_lower:
        depart_time = "17:00"
    else:
        # Regex for HH:MM or H pm / am
        time_match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', text_lower)
        if time_match:
            hr = int(time_match.group(1))
            mn = int(time_match.group(2)) if time_match.group(2) else 0
            meridiem = time_match.group(3)
            if meridiem == "pm" and hr < 12:
                hr += 12
            elif meridiem == "am" and hr == 12:
                hr = 0
            if 0 <= hr <= 23:
                depart_time = f"{hr:02d}:{mn:02d}"

    # 2. Sun tolerance extraction
    # Default to low if mentions dadu, elderly, baby, sensitive, or "can't take much sun"
    sun_tolerance = "medium"
    if any(w in text_lower for w in ["can't take", "cant take", "no sun", "avoid sun", "sensitive", "elderly", "dadu", "grandpa", "skin", "patient", "low tolerance", "minimum sun", "shaded only"]):
        sun_tolerance = "low"
    elif any(w in text_lower for w in ["fine with sun", "don't mind", "sun is fine", "quickest", "high tolerance", "fastest"]):
        sun_tolerance = "high"

    # 3. Walking speed extraction
    speed_kmh = 3.5
    if any(w in text_lower for w in ["dadu", "elderly", "slow", "stroll", "gently", "cane", "walking stick", "weak"]):
        speed_kmh = 2.8
    elif any(w in text_lower for w in ["brisk", "hurry", "rush", "fast", "jog", "quick"]):
        speed_kmh = 4.5
        
    # Check if explicit speed mentioned (e.g. 3 km/h or 3 kmh)
    speed_match = re.search(r'\b(\d(?:\.\d)?)\s*(?:km/h|kmh|kmph)\b', text_lower)
    if speed_match:
        try:
            speed_kmh = float(speed_match.group(1))
        except:
            pass

    # 4. Origin & Destination extraction
    origin = "home"
    destination = "the clinic"
    
    # Look for "from <origin> to <destination>" pattern
    from_to = re.search(r'from\s+([a-z0-9\s\']+?)\s+to\s+([a-z0-9\s\']+?)(?:\s+at|\s+around|\s+for|\s+he|\s+with|\s+because|$|\.)', text_lower)
    to_from = re.search(r'(?:walk|take|go|head|rush|stroll)(?:\s+[a-z\']+)*\s+to\s+([a-z0-9\s\']+?)\s+from\s+([a-z0-9\s\']+?)(?:\s+at|\s+around|\s+for|\s+he|\s+with|\s+because|$|\.)', text_lower)
    
    if from_to:
        origin = from_to.group(1).strip()
        destination = from_to.group(2).strip()
    elif to_from:
        destination = to_from.group(1).strip()
        origin = to_from.group(2).strip()
    else:
        # Look for "take dadu to <dest>" or "walk to <dest>"
        walk_to = re.search(r'(?:walk|take|go|head|bring|rush|stroll)(?:\s+[a-z\']+)*\s+to\s+([a-z0-9\s\']+?)(?:\s+at|\s+around|\s+for|\s+he|\s+with|\s+from|\s+because|$|\.)', text_lower)
        if walk_to:
            destination = walk_to.group(1).strip()
            # If from is specified later
            from_match = re.search(r'from\s+([a-z0-9\s\']+?)(?:\s+at|\s+around|\s+to|\s+he|$|\.)', text_lower)
            if from_match:
                origin = from_match.group(1).strip()
            else:
                origin = "home"

    # Clean destination and origin strings
    for noise in ["the ", "a ", "our ", "my "]:
        if origin.startswith(noise):
            origin = origin[len(noise):]
        if destination.startswith(noise):
            destination = destination[len(noise):]
            
    return {
        "origin": origin,
        "destination": destination,
        "depart_time": depart_time,
        "sun_tolerance": sun_tolerance,
        "speed_kmh": round(speed_kmh, 1),
        "parser_source": "offline_deterministic"
    }


def parse_request_with_llm(text: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Parses request using open model on Groq (or local Ollama / fallback).
    Always returns structured JSON matching contract.
    """
    groq_key = api_key or os.environ.get("GROQ_API_KEY")
    
    if groq_key and HAS_GROQ:
        try:
            client = Groq(api_key=groq_key)
            prompt = f"""You are the Chhaya Kolkata Shade Routing Agent.
A user says: "{text}"

Extract the walking parameters into valid JSON with this exact schema:
{{
  "origin": "string (e.g. home, flurys, oxford bookstore, russell street)",
  "destination": "string (e.g. clinic, belle vue, camac square, park clinic)",
  "depart_time": "HH:MM in 24-hr format (e.g. 15:00)",
  "sun_tolerance": "low" | "medium" | "high",
  "speed_kmh": number (typically 2.8 to 4.5, default 3.0 for elderly or patients)
}}
Output ONLY valid JSON, no markdown formatting, no comments."""

            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a precise JSON extractor for Kolkata shade routing."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            raw = chat_completion.choices[0].message.content
            parsed = json.loads(raw)
            parsed["parser_source"] = "groq_llama_3.3_70b"
            return parsed
        except Exception as e:
            print(f"Groq parsing failed ({e}), falling back to offline deterministic parser.")

    # Check local Ollama
    if HAS_HTTPX:
        try:
            r = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:7b",
                    "prompt": f'Extract to JSON: origin, destination, depart_time, sun_tolerance, speed_kmh from: "{text}". Return valid JSON only.',
                    "format": "json",
                    "stream": False
                },
                timeout=2.0
            )
            if r.status_code == 200:
                data = json.loads(r.json()["response"])
                data["parser_source"] = "local_ollama"
                return data
        except Exception:
            pass

    # Fast offline fallback
    return offline_parse_request(text)
