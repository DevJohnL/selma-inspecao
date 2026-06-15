"""Carrega as variáveis de ambiente do .env (desacoplado do app Next.js)."""
import os

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

# Groq (usado na geração do relatório, em vez do Gemini)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

# Telegram + link do formulário na nuvem do Streamlit
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
STREAMLIT_APP_URL = os.getenv("STREAMLIT_APP_URL", "http://localhost:8501").strip().rstrip("/")

# WhatsApp via Evolution API
EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://localhost:8080").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "default").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()
WHATSAPP_BOT_PORT = int(os.getenv("WHATSAPP_BOT_PORT", "8080"))


def missing_db_config() -> list[str]:
    faltando = []
    if not SUPABASE_URL:
        faltando.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        faltando.append("SUPABASE_SERVICE_ROLE_KEY")
    return faltando


def missing_ai_config() -> list[str]:
    return [] if GROQ_API_KEY else ["GROQ_API_KEY"]
