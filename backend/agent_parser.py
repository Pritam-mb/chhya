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

# Open-weight models available on Groq. `llama-3.3-70b-versatile` was retired;
# gpt-oss and qwen are the current open-weight options (override with GROQ_MODEL).
GROQ_MODEL_CANDIDATES = [
    os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
]


DEFAULT_POIS = [
    {"name": "Dadu's Residence (Middleton Row)", "aliases": ["home", "dadu's home", "house", "residence", "middleton row", "dadu"]},
    {"name": "Belle Vue Clinic", "aliases": ["clinic", "the clinic", "belle vue", "belle vue clinic", "doctor", "hospital", "dispensary"]},
    {"name": "Park Clinic", "aliases": ["park clinic", "gorky terrace clinic"]},
    {"name": "Flurys Tea Room", "aliases": ["flurys", "tea room", "bakery", "cafe", "park street tea room"]},
    {"name": "Oxford Bookstore", "aliases": ["oxford bookstore", "bookstore", "books", "oxford"]},
    {"name": "Camac Street Mall & Offices", "aliases": ["camac street", "camac square", "offices", "mall"]},
    {"name": "Russell Street Market & Pharmacy", "aliases": ["russell street", "pharmacy", "market", "chemist"]}
]


# Romanized Bengali / Hindi vocabulary mapped to the English tokens the
# deterministic parser already understands. Keeps the offline fallback usable
# for the code-mixed requests the challenge asks about (F9).
_ML_PLACES = {
    r"\bbari\b": "home",
    r"\bbadi\b": "home",
    r"\bghor\b": "home",
    r"\bghar\b": "home",
    r"\bbasha\b": "home",
    r"\bklinik\b": "clinic",
    r"\bdaktar\b": "doctor",
    r"\bdaktarkhana\b": "doctor",
    r"\bhospital\b": "clinic",
    r"\bbazaar\b": "market",
    r"\bbazar\b": "market",
    r"\bdukkan\b": "pharmacy",
    r"\bdokan\b": "pharmacy",
    r"\bmedicine\b": "pharmacy",
    r"\bboi\b": "bookstore",
    r"\bkitab\b": "bookstore",
    r"\bchai\b": "tea",
}


def _normalize_multilingual(text: str) -> str:
    """Rewrites common romanized Bengali/Hindi words into English tokens."""
    t = text.lower().strip()
    for pat, rep in _ML_PLACES.items():
        t = re.sub(pat, rep, t)

    # Time-of-day words
    t = re.sub(r"\bdupure?\b|\bdopahar\w*\b", "noon", t)
    t = re.sub(r"\bsubaha?\b|\bshokal\w*\b|\bsokal\w*\b|\bsubahe\b", "morning", t)
    t = re.sub(r"\bbikal\w*\b|\bbikel\w*\b|\bshaam\w*\b|\bsham\b", "evening", t)

    is_morning = bool(re.search(r"\bmorning\b", t))

    def _hour(m: "re.Match") -> str:
        h = int(m.group(1))
        if is_morning and h <= 11:
            return f"{h} am"
        return f"{h} pm"

    t = re.sub(r"\b(\d{1,2})\s*(?:tay|baje|bje|ta|te)\b", _hour, t)

    # Speed words
    t = re.sub(r"\bdhire\w*\b|\baste\w*\b|\bdheere\b|\baaram\w*\b", "slow", t)
    t = re.sub(r"\bjaldi\w*\b|\btez\b|\bjhat\b", "fast", t)
    return t


def offline_parse_request(text: str) -> Dict[str, Any]:
    """
    Deterministic rule-based & regex semantic extractor that runs 100% offline
    on the host machine without internet, satisfying P0-4 and acceptance checks.
    Understands English plus romanized Bengali/Hindi (see _normalize_multilingual).
    """
    text_lower = _normalize_multilingual(text)
    
    # 1. Depart time extraction
    depart_time = "15:00"  # default

    def _fmt(hr: int, mn: int, meridiem: Optional[str]) -> Optional[str]:
        if meridiem == "pm" and hr < 12:
            hr += 12
        elif meridiem == "am" and hr == 12:
            hr = 0
        if 0 <= hr <= 23 and 0 <= mn <= 59:
            return f"{hr:02d}:{mn:02d}"
        return None

    # Explicit HH:MM (optionally followed by am/pm), then "H am/pm", then
    # time-of-day words, then a bare-number last resort.
    hhmm = re.search(r'\b(\d{1,2}):(\d{2})\s*(am|pm)?\b', text_lower)
    hmer = re.search(r'\b(\d{1,2})\s*(am|pm)\b', text_lower)

    if hhmm:
        depart_time = _fmt(int(hhmm.group(1)), int(hhmm.group(2)), hhmm.group(3)) or depart_time
    elif hmer:
        depart_time = _fmt(int(hmer.group(1)), 0, hmer.group(2)) or depart_time
    elif re.search(r'\bnoon\b', text_lower) or "12 pm" in text_lower or "12pm" in text_lower:
        depart_time = "12:00"
    elif "morning" in text_lower:
        depart_time = "09:00"
    elif "evening" in text_lower:
        depart_time = "17:00"
    else:
        time_match = re.search(r'\b(\d{1,2})\b', text_lower)
        if time_match and "km/h" not in text_lower[max(0, time_match.start() - 8):time_match.end() + 8]:
            depart_time = _fmt(int(time_match.group(1)), 0, None) or depart_time

    # 2. Sun tolerance extraction
    # Default to low if mentions dadu, elderly, baby, sensitive, or "can't take much sun"
    sun_tolerance = "medium"
    if any(w in text_lower for w in ["can't take", "cant take", "no sun", "avoid sun", "sensitive", "elderly", "dadu", "grandpa", "skin", "patient", "low tolerance", "minimum sun", "shaded only", "shade", "shaded", "roddur", "rod", "dhup", "dhoop", "gorom", "shojjo", "shojjho", "sun se", "avoid", "chhaya", "chaya"]):
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
    # Bengali/Hindi "X theke Y" / "X se Y" means "from X to Y"
    ml_route = re.search(r"([a-z0-9\s\']+?)\s+(?:theke|se)\s+([a-z0-9\s\']+?)(?=\s+\d|\s+at|\s+around|\s+for|\s+morning|\s+noon|\s+evening|$|\.)", text_lower)
    # Bengali/Hindi "dadu ke <dest> niye chalo" / "dadu ko <dest> le jao"
    ml_dest = re.search(r"\b(?:ke|ko)\s+([a-z0-9\s\']+?)\s+(?:niye|le|nio|leke|chalo)\b", text_lower)

    if ml_route:
        origin = ml_route.group(1).strip()
        destination = ml_route.group(2).strip()
    elif ml_dest:
        destination = ml_dest.group(1).strip()
        if not origin:
            origin = "home"
    elif from_to:
        origin = from_to.group(1).strip()
        destination = from_to.group(2).strip()
    elif to_from:
        destination = to_from.group(1).strip()
        origin = to_from.group(2).strip()
    else:
        # Look for "take dadu to <dest>" or "walk to <dest>"
        walk_to = re.search(r'(?:walk|take|go|head|bring|rush|stroll)(?:\s+[a-z\']+)*\s+to\s+([a-z0-9\s\']+?)(?:\s+at|\s+around|\s+for|\s+he|\s+with|\s+from|\s+because|\s+\d|\s*,|\s+morning|\s+noon|\s+evening|$|\.)', text_lower)
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
        client = Groq(api_key=groq_key)
        for model_name in GROQ_MODEL_CANDIDATES:
            try:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a precise JSON extractor for Kolkata shade routing."},
                        {"role": "user", "content": prompt}
                    ],
                    model=model_name,
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                raw = chat_completion.choices[0].message.content
                parsed = json.loads(raw)
                parsed["parser_source"] = f"groq:{model_name}"
                return parsed
            except Exception as e:
                print(f"Groq parsing with {model_name} failed ({e}).")
        print("All Groq models failed, falling back to offline deterministic parser.")

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
