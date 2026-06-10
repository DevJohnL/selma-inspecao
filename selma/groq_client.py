"""Cliente mínimo da Groq (API compatível com OpenAI Chat Completions) via HTTP.

Espelha a interface de selma/gemini.py — mesmos prompts (PT-BR), temperatura 0.2
e modelo configurável (GROQ_MODEL, default llama-3.3-70b-versatile). Usado pela
geração do relatório (selma/report.py) no lugar do Gemini.
"""
import requests

from . import config

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


def _humanize_column(col: str) -> str:
    base = col
    if base.lower().endswith("_url"):
        base = base[:-4]
    return " ".join(w.capitalize() for w in base.replace("_", " ").split()).strip()


def _call_groq(prompt: str, max_output_tokens: int = 700) -> str:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY não configurada")
    res = requests.post(
        _ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
        },
        json={
            "model": config.GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_output_tokens,
        },
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Groq API erro {res.status_code}: {res.text[:500]}")
    data = res.json()
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        text = ""
    if not text:
        raise RuntimeError("Groq não retornou texto")
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
    return _call_groq(prompt, 512)


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
    return _call_groq(prompt, 700)


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
    return _call_groq(prompt, 700)
