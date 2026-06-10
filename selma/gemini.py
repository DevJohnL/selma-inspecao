"""Cliente mínimo do Gemini (Google Generative Language API) via HTTP.

Port de supabase/functions/_shared/gemini.ts — mesmos prompts (PT-BR),
temperatura 0.2 e modelo configurável (GEMINI_MODEL, default gemini-2.0-flash).
"""
import requests

from . import config

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


def _humanize_column(col: str) -> str:
    base = col
    if base.lower().endswith("_url"):
        base = base[:-4]
    return " ".join(w.capitalize() for w in base.replace("_", " ").split()).strip()


def _call_gemini(prompt: str, max_output_tokens: int = 700) -> str:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")
    url = f"{_ENDPOINT}/{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
    res = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_output_tokens},
        },
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Gemini API erro {res.status_code}: {res.text[:500]}")
    data = res.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError):
        text = ""
    if not text:
        raise RuntimeError("Gemini não retornou texto")
    return text


def summarize_responses(part_label: str, answers: dict) -> str:
    lines = []
    for col, v in answers.items():
        if v is None or str(v).strip() == "":
            continue
        value = v if isinstance(v, str) else str(v)
        lines.append(f"- {_humanize_column(col)}: {value}")
    if not lines:
        return "Sem respostas preenchidas para resumir."
    prompt = (
        "Você é um assistente técnico de inspeções elétricas. Gere um resumo "
        "objetivo e curto (3 a 5 frases), em português do Brasil, da seção "
        f'"{part_label}" de uma ordem de serviço, destacando o estado dos '
        "equipamentos, valores relevantes e eventuais problemas/pendências. "
        "Não invente dados que não estejam abaixo. Ignore campos de foto (URLs).\n\n"
        "Respostas:\n" + "\n".join(lines)
    )
    return _call_gemini(prompt, 512)


def generate_report_section(section_label: str, content: str) -> str:
    trimmed = (content or "").strip()
    if not trimmed:
        return "Seção não preenchida nesta ordem de serviço."
    prompt = (
        "Você é um engenheiro eletricista redigindo um relatório técnico de inspeção "
        "de subestação. Escreva, em português do Brasil, um parágrafo técnico e objetivo "
        f'para a seção "{section_label}" do relatório, com base SOMENTE nas informações '
        "abaixo. Não invente dados. Destaque o estado dos equipamentos, valores medidos "
        "relevantes e eventuais não-conformidades.\n\nInformações coletadas:\n" + trimmed
    )
    return _call_gemini(prompt, 700)


def generate_recommendations(sections_overview: str) -> str:
    trimmed = (sections_overview or "").strip()
    if not trimmed:
        return "Sem dados suficientes para gerar recomendações."
    prompt = (
        "Você é um engenheiro eletricista. Com base no panorama abaixo de uma inspeção "
        "de subestação, liste de forma objetiva (em português do Brasil) as principais "
        "recomendações, pendências e ações corretivas. Use itens curtos. Priorize "
        "segurança e itens fora de conformidade. Não invente dados.\n\n"
        "Panorama da inspeção:\n" + trimmed
    )
    return _call_gemini(prompt, 700)
