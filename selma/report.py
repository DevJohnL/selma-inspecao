"""Geração do relatório consolidado por IA (Gemini), feita diretamente aqui no
script (sem edge functions). Port de generate-os-report + summarize-checklist-part.

Fluxo:
  1. Para cada parte com linha gravada, gera um resumo (Gemini) e grava em
     `checklist_part_summary` (upsert por service_order_id, part_key, instance).
  2. Agrega os resumos por coluna do relatório, pede ao Gemini um parágrafo
     técnico por seção + recomendações, e grava 1 linha em `relatory`.
"""
from . import db, gemini
from .registry import get_part

# Mapeia cada coluna de `relatory` para as partes do checklist que a alimentam.
REPORT_COLUMNS = [
    {"column": "entrada_alimentacao", "label": "Entrada de Alimentação",
     "parts": ["power_supply_input"]},
    {"column": "quadro_protecao_geral",
     "label": "Quadro de Proteção Geral / Proteção de Média Tensão",
     "parts": ["general_protection_panel", "medium_voltage_protection"]},
    {"column": "transformador", "label": "Transformador",
     "parts": ["transformer_inspection", "coil_resistance_test",
               "insulation_resistance_test", "transformation_ratio_test"]},
    {"column": "quadro_geral_baixa_tensao", "label": "Quadro Geral de Baixa Tensão (QGBT)",
     "parts": ["low_voltage_main_panel"]},
    {"column": "banco_capacitores", "label": "Banco de Capacitores",
     "parts": ["capacitor_bank"]},
    {"column": "servicos_realizados", "label": "Serviços Realizados",
     "parts": ["additional_services_executed", "general_observations"]},
]


def _humanize(col: str) -> str:
    base = col[:-4] if col.lower().endswith("_url") else col
    return " ".join(w.capitalize() for w in base.replace("_", " ").split()).strip()


def _raw_content_for(service_order_id: int, part_key: str) -> str:
    part = get_part(part_key)
    if not part:
        return ""
    res = (
        db.client().table(part.table).select(",".join(part.columns))
        .eq(part.fk_column, service_order_id).execute()
    )
    rows = res.data or []
    chunks = []
    for row in rows:
        pieces = [
            f"{_humanize(k)}: {v}"
            for k, v in row.items()
            if v is not None and str(v).strip() != ""
        ]
        if pieces:
            chunks.append("; ".join(pieces))
    return "\n".join(chunks)


def _summarize_filled_parts(service_order_id: int) -> dict[str, list[str]]:
    """Gera e grava resumos para cada parte com dados; devolve part_key -> [resumos]."""
    sb = db.client()
    summaries: dict[str, list[str]] = {}
    for part_key in db.CHECKLIST_PART_ORDER:
        part = get_part(part_key)
        res = (
            sb.table(part.table).select(",".join(part.columns))
            .eq(part.fk_column, service_order_id).execute()
        )
        rows = res.data or []
        for row in rows:
            answers = {k: v for k, v in row.items() if k in part.columns}
            instance = 0
            if part.instance_column:
                instance = int(row.get(part.instance_column) or 1)
            summary = gemini.summarize_responses(part.label, answers)
            sb.table("checklist_part_summary").upsert(
                {
                    "service_order_id": service_order_id,
                    "part_key": part.key,
                    "instance_number": instance,
                    "summary": summary,
                },
                on_conflict="service_order_id,part_key,instance_number",
            ).execute()
            summaries.setdefault(part.key, []).append(summary.strip())
    return summaries


def generate_full_report(os_number: int, service_order_id: int) -> dict:
    summaries = _summarize_filled_parts(service_order_id)

    def content_for(parts: list[str]) -> str:
        chunks = []
        for part_key in parts:
            if summaries.get(part_key):
                chunks.append("\n".join(summaries[part_key]))
            else:
                raw = _raw_content_for(service_order_id, part_key)
                if raw:
                    chunks.append(raw)
        return "\n\n".join(c for c in chunks if c)

    report: dict[str, str] = {}
    overview = []
    for col in REPORT_COLUMNS:
        content = content_for(col["parts"])
        report[col["column"]] = gemini.generate_report_section(col["label"], content)
        if content:
            overview.append(f"## {col['label']}\n{content}")

    report["recomendacoes"] = gemini.generate_recommendations("\n\n".join(overview))

    # Grava/atualiza a linha em `relatory` (uma por OS).
    sb = db.client()
    existing = (
        sb.table("relatory").select("id").eq("numero_os", os_number).limit(1).execute()
    ).data
    if existing:
        sb.table("relatory").update(report).eq("id", existing[0]["id"]).execute()
    else:
        sb.table("relatory").insert({"numero_os": os_number, **report}).execute()

    return report
