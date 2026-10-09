import os
import json
import base64
from typing import Optional, Dict, Any
import httpx

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
# JBFqnCBsd6RMkjVDRZzb (George) is the default standard narrator voice available to all free & paid API users
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"

async def synthesize_briefing_audio(text: str, voice_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Synthesizes speech using ElevenLabs API if key is available,
    otherwise provides seamless fallback metadata for browser speech synthesis.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    target_voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
    
    if not api_key:
        return {
            "has_audio": False,
            "provider": "browser_web_speech",
            "voice_id": target_voice,
            "text": text,
            "note": "ELEVENLABS_API_KEY not configured. Seamless browser voice synthesis active."
        }
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }

    # Attempt with modern supported models (eleven_multilingual_v2, eleven_flash_v2_5)
    models_to_try = ["eleven_multilingual_v2", "eleven_flash_v2_5"]
    voices_to_try = [target_voice]
    if target_voice != DEFAULT_VOICE_ID:
        voices_to_try.append(DEFAULT_VOICE_ID)

    last_error = ""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for v_id in voices_to_try:
                url = f"{ELEVENLABS_API_URL}/{v_id}"
                for m_id in models_to_try:
                    payload = {
                        "text": text,
                        "model_id": m_id,
                        "voice_settings": {
                            "stability": 0.65,
                            "similarity_boost": 0.75
                        }
                    }
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200 and len(resp.content) > 100:
                        audio_b64 = base64.b64encode(resp.content).decode("utf-8")
                        return {
                            "has_audio": True,
                            "provider": "elevenlabs",
                            "voice_id": v_id,
                            "model_id": m_id,
                            "audio_base64": audio_b64,
                            "audio_mime": "audio/mpeg",
                            "text": text
                        }
                    else:
                        last_error = f"ElevenLabs API error ({resp.status_code}): {resp.text}"
                        # If payment required for this specific voice, continue to fallback voice
                        if resp.status_code == 402:
                            break
    except Exception as e:
        last_error = str(e)

    # If API call failed, provide graceful browser Web Speech API fallback
    return {
        "has_audio": False,
        "provider": "browser_web_speech",
        "error": last_error,
        "text": text
    }
