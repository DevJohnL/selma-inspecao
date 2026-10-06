"""Geração do relatório consolidado por IA.

O motor é único e vive na edge function `generate-os-report` do Supabase (a chave
da IA fica nos secrets da função, nunca aqui). Este módulo apenas a chama e
devolve o texto de cada seção; a própria função grava a linha em `relatory`.
"""
import requests

from . import config

_TIMEOUT_SECONDS = 150


def generate_full_report(os_number: int, service_order_id: int | None = None) -> dict:
    """Gera (ou regenera) o relatório da OS e devolve {coluna_do_relatorio: texto}."""
    if not config.OS_LOOKUP_API_KEY:
        raise RuntimeError(
            "OS_LOOKUP_API_KEY não configurada (chave de acesso às edge functions)."
        )

    try:
        res = requests.post(
            f"{config.SUPABASE_URL}/functions/v1/generate-os-report",
            headers={
                "Content-Type": "application/json",
                "x-api-key": config.OS_LOOKUP_API_KEY,
            },
            json={"os_number": os_number},
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.Timeout as e:
        raise RuntimeError("A geração do relatório demorou demais. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Não consegui falar com o serviço de relatório: {e}") from e

    try:
        data = res.json()
    except ValueError:
        data = {}

    if not res.ok:
        code = data.get("error") or f"http_{res.status_code}"
        detail = data.get("detail") or res.text[:300]
        if code == "ai_config_error":
            raise RuntimeError(
                "A chave da IA do relatório está ausente ou inválida. "
                f"Avise o administrador para atualizar o secret GROQ_API_KEY. ({detail})"
            )
        raise RuntimeError(f"Falha ao gerar o relatório ({code}): {detail}")

    return data.get("report") or {}
