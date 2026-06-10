"""Camada de acesso ao Supabase, replicando a lógica das edge functions:
get-os-by-phone, save-checklist-part, update-os-progress (_shared/progress.ts).

Usa a Service Role Key (ignora RLS), exatamente como `getServiceClient`.
"""
from functools import lru_cache

from supabase import Client, create_client

from . import config
from .registry import CHECKLIST_PART_ORDER, CHECKLIST_REGISTRY, get_part

ACTIVE_STATUSES = ["pending", "in_progress", "awaiting_report"]


@lru_cache(maxsize=1)
def client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


# --------------------------------------------------------------------------
# Telefone / OS (port de _shared/http.ts buildPhoneCandidates + get-os-by-phone)
# --------------------------------------------------------------------------

def build_phone_candidates(raw: str) -> list[int]:
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return []
    candidates = {digits}
    if len(digits) in (12, 13) and digits.startswith("55"):
        candidates.add(digits[2:])
    if len(digits) in (10, 11):
        candidates.add("55" + digits)
    out = []
    for d in candidates:
        if len(d) <= 15:
            n = int(d)
            if n > 0:
                out.append(n)
    return out


def find_technical_by_phone(phone: str) -> dict | None:
    candidates = build_phone_candidates(phone)
    if not candidates:
        return None
    res = (
        client().table("technical").select("id, name, phone")
        .in_("phone", candidates).limit(1).execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def list_active_orders(technical_id: int) -> list[dict]:
    def _query(columns: str, only_active: bool):
        q = client().table("service_order").select(columns).eq("technical", technical_id)
        if only_active:
            q = q.in_("status", ACTIVE_STATUSES)
        return q.order("created_at", desc=True).execute()

    full = ("os_number, schedule, status, start_time, shutdown, "
            "checklist_parts, completed_parts, next_part, client(name)")
    minimal = "os_number, schedule, status, start_time, shutdown, client(name)"

    def _run(only_active: bool):
        try:
            return _query(full, only_active)
        except Exception:  # noqa: BLE001 - colunas de progresso podem não existir no banco
            return _query(minimal, only_active)

    res = _run(only_active=True)
    # Fallback: se nenhuma OS "ativa" aparecer, mostra todas as OS do técnico
    # (o banco pode ter status nulo/diferente dos esperados).
    if not (res.data or []):
        res = _run(only_active=False)
    orders = []
    for o in res.data or []:
        parts = o.get("checklist_parts") or []
        completed = o.get("completed_parts") or []
        client_obj = o.get("client") or {}
        orders.append({
            "os_number": o.get("os_number"),
            "schedule": o.get("schedule"),
            "status": o.get("status"),
            "start_time": o.get("start_time"),
            "shutdown": o.get("shutdown"),
            "checklist_parts": parts,
            "completed_parts": completed,
            "next_part": o.get("next_part") or (parts[0] if parts else None),
            "progress": (len(completed) / len(parts)) if parts else 0,
            "client_name": client_obj.get("name") if isinstance(client_obj, dict) else None,
        })
    return orders


def resolve_service_order_id(os_number: int) -> int | None:
    res = (
        client().table("service_order").select("id")
        .eq("os_number", os_number).limit(1).execute()
    )
    rows = res.data or []
    return rows[0]["id"] if rows else None


# --------------------------------------------------------------------------
# Salvamento (port de save-checklist-part)
# --------------------------------------------------------------------------

def save_checklist_part(os_number: int, part_key: str, data: dict,
                        instance: int = 1, mark_complete: bool = True) -> dict:
    part = get_part(part_key)
    if not part:
        raise ValueError(f"invalid_part: {part_key}")

    service_order_id = resolve_service_order_id(os_number)
    if service_order_id is None:
        raise ValueError(f"service_order_not_found: {os_number}")

    # Whitelist: descarta chaves desconhecidas.
    filtered = {k: v for k, v in data.items() if k in part.columns}
    if not filtered:
        return {"skipped": True, "reason": "no_valid_columns"}

    record = {part.fk_column: service_order_id, **filtered}
    if part.instance_column:
        record[part.instance_column] = instance

    sb = client()
    if part.append_only:
        saved = sb.table(part.table).insert(record).execute().data
    else:
        on_conflict = (
            f"{part.fk_column},{part.instance_column}"
            if part.instance_column else part.fk_column
        )
        saved = sb.table(part.table).upsert(record, on_conflict=on_conflict).execute().data

    progress = None
    if mark_complete:
        progress = apply_progress(service_order_id, completed_part=part.key)

    return {"ok": True, "saved": saved, "progress": progress,
            "service_order_id": service_order_id}


# --------------------------------------------------------------------------
# Andamento (port de _shared/progress.ts)
# --------------------------------------------------------------------------

def _sort_by_order(parts) -> list[str]:
    s = set(parts)
    return [k for k in CHECKLIST_PART_ORDER if k in s]


def _detect_filled_parts(service_order_id: int) -> list[str]:
    sb = client()
    filled = []
    for part in CHECKLIST_REGISTRY:
        res = (
            sb.table(part.table).select("id", count="exact")
            .eq(part.fk_column, service_order_id).limit(1).execute()
        )
        if (res.count or 0) > 0:
            filled.append(part.key)
    return filled


def apply_progress(service_order_id: int, completed_part: str | None = None,
                   recompute: bool = False) -> dict:
    sb = client()
    try:
        so = (
            sb.table("service_order")
            .select("checklist_parts, completed_parts, status")
            .eq("id", service_order_id).single().execute()
        ).data or {}
        has_progress_cols = True
    except Exception:  # noqa: BLE001 - banco sem colunas de progresso
        so = (
            sb.table("service_order").select("status")
            .eq("id", service_order_id).single().execute()
        ).data or {}
        has_progress_cols = False

    selected = so.get("checklist_parts") or []
    completed_set = set(so.get("completed_parts") or [])

    if completed_part and get_part(completed_part):
        completed_set.add(completed_part)
    if recompute:
        for key in _detect_filled_parts(service_order_id):
            completed_set.add(key)

    universe = selected if selected else CHECKLIST_PART_ORDER
    completed_parts = _sort_by_order([k for k in completed_set if k in universe])
    completed_lookup = set(completed_parts)
    ordered_universe = _sort_by_order(universe)
    next_part = next((k for k in ordered_universe if k not in completed_lookup), None)

    status = so.get("status") or "pending"
    if next_part is None and completed_parts:
        if status in ("pending", "in_progress"):
            status = "awaiting_report"
    elif completed_parts and status == "pending":
        status = "in_progress"

    update = {"status": status}
    if has_progress_cols:
        update["completed_parts"] = completed_parts
        update["next_part"] = next_part
    try:
        sb.table("service_order").update(update).eq("id", service_order_id).execute()
    except Exception:  # noqa: BLE001 - se faltar coluna, atualiza só o status
        sb.table("service_order").update({"status": status}).eq("id", service_order_id).execute()

    return {"completed_parts": completed_parts, "next_part": next_part, "status": status}
