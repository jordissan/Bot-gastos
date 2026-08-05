# Env vars dummy para poder importar bot.py en tests sin tocar servicios reales.
# Sin GROQ_API_KEY ni GOOGLE_*: el bot cae a parser clásico y reglas puras.
import os

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("NOTION_TOKEN", "test-token")
os.environ.setdefault("NOTION_DATABASE_ID", "test-db-id")
