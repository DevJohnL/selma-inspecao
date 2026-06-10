"""Carrega as variáveis de ambiente do .env (desacoplado do app Next.js)."""
import os

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

# Telegram + link do formulário na nuvem do Streamlit
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
STREAMLIT_APP_URL = os.getenv("STREAMLIT_APP_URL", "http://localhost:8501").strip().rstrip("/")


def missing_db_config() -> list[str]:
    faltando = []
    if not SUPABASE_URL:
        faltando.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        faltando.append("SUPABASE_SERVICE_ROLE_KEY")
    return faltando


def missing_ai_config() -> list[str]:
    return [] if GEMINI_API_KEY else ["GEMINI_API_KEY"]
