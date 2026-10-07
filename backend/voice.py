import os
import json
from typing import Optional, Dict, Any
import httpx

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (calm, clear voice)

async def synthesize_briefing_audio(text: str, voice_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Synthesizes speech using ElevenLabs API if key is available,
    otherwise provides seamless fallback metadata for browser speech synthesis.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    target_voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    
    if not api_key:
        return {
            "has_audio": False,
            "provider": "browser_web_speech",
            "voice_id": target_voice,
            "text": text,
            "note": "ELEVENLABS_API_KEY not configured. Seamless browser voice synthesis active."
        }
        
    url = f"{ELEVENLABS_API_URL}/{target_voice}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.65,
            "similarity_boost": 0.75
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                # Return binary audio bytes or base64
                import base64
                audio_b64 = base64.b64encode(resp.content).decode("utf-8")
                return {
                    "has_audio": True,
                    "provider": "elevenlabs",
                    "voice_id": target_voice,
                    "audio_base64": audio_b64,
                    "audio_mime": "audio/mpeg",
                    "text": text
                }
            else:
                return {
                    "has_audio": False,
                    "provider": "browser_web_speech",
                    "error": f"ElevenLabs API error: {resp.status_code} - {resp.text}",
                    "text": text
                }
    except Exception as e:
        return {
            "has_audio": False,
            "provider": "browser_web_speech",
            "error": str(e),
            "text": text
        }
