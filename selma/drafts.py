"""Ponte de dados entre o bot do Telegram e o formulário no Streamlit.

O bot grava um rascunho (respostas em JSON) com um token; o Streamlit lê pelo
token recebido na URL (?draft=<token>). Usa o mesmo client Service Role do db.py.
"""
import secrets

from . import db


def create_draft(os_number: int, service_order_id: int | None,
                 technical: dict | None, answers: list[dict]) -> str:
    token = secrets.token_urlsafe(8)
    db.client().table("inspection_draft").insert({
        "token": token,
        "os_number": os_number,
        "service_order_id": service_order_id,
        "technical_id": (technical or {}).get("id"),
        "technical_name": (technical or {}).get("name"),
        "answers": answers,
        "status": "pending_review",
    }).execute()
    return token


def start_draft(os_number: int, service_order_id: int | None,
                technical: dict | None) -> str:
    """Cria um rascunho vazio "em preenchimento" para salvar a cada resposta."""
    token = secrets.token_urlsafe(8)
    db.client().table("inspection_draft").insert({
        "token": token,
        "os_number": os_number,
        "service_order_id": service_order_id,
        "technical_id": (technical or {}).get("id"),
        "technical_name": (technical or {}).get("name"),
        "answers": [],
        "status": "in_progress",
    }).execute()
    return token


def save_answers(token: str, answers: list[dict]) -> None:
    """Grava a lista completa de respostas (chamado a cada pergunta respondida)."""
    db.client().table("inspection_draft").update(
        {"answers": answers}
    ).eq("token", token).execute()


def find_open_draft(os_number: int, technical_id: int | None) -> dict | None:
    """Rascunho mais recente da OS ainda não salvo (para retomar de onde parou)."""
    q = (
        db.client().table("inspection_draft").select("*")
        .eq("os_number", os_number)
        .in_("status", ["in_progress", "pending_review"])
    )
    if technical_id is not None:
        q = q.eq("technical_id", technical_id)
    rows = q.order("created_at", desc=True).limit(1).execute().data or []
    return rows[0] if rows else None


def get_draft(token: str) -> dict | None:
    res = (
        db.client().table("inspection_draft").select("*")
        .eq("token", token).limit(1).execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def finish_draft(token: str, answers: list[dict]) -> None:
    """Fim das perguntas no bot: grava as respostas e libera a revisão no Streamlit."""
    db.client().table("inspection_draft").update(
        {"answers": answers, "status": "pending_review"}
    ).eq("token", token).execute()


def mark_saved(token: str) -> None:
    db.client().table("inspection_draft").update(
        {"status": "saved"}
    ).eq("token", token).execute()
