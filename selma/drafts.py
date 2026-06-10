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


def get_draft(token: str) -> dict | None:
    res = (
        db.client().table("inspection_draft").select("*")
        .eq("token", token).limit(1).execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def mark_saved(token: str) -> None:
    db.client().table("inspection_draft").update(
        {"status": "saved"}
    ).eq("token", token).execute()
