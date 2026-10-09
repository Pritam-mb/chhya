import os

# Keep the test suite hermetic: no telemetry to Sentry and no network/credits
# burned on the hosted Groq/ElevenLabs APIs. load_dotenv() does not override
# existing vars, so empty strings here reliably force the offline code paths.
os.environ["SENTRY_DSN"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["ELEVENLABS_API_KEY"] = ""
