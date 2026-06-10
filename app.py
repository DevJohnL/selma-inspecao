"""Selma — Inspeção de OS (versão Python/Streamlit, desacoplada do app Next.js).

Reproduz o fluxo Typebot de `automacao/*.json` como um chat estilo WhatsApp,
mostra uma tela de revisão editável e, após confirmação, salva direto no
Supabase e gera o relatório por IA (Gemini) — tudo neste script.

Rodar:  streamlit run app.py
"""
import html
import os

import streamlit as st
import streamlit.components.v1 as components

# Na nuvem do Streamlit os segredos ficam em st.secrets e não em os.environ.
# Copiamos para o ambiente ANTES de importar `selma` (config lê via os.getenv).
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:  # noqa: BLE001 - sem secrets.toml (rodando local com .env)
    pass

from selma import config, db, drafts, flow  # noqa: E402
from selma import report as report_mod  # noqa: E402
from selma.registry import get_part  # noqa: E402

st.set_page_config(page_title="Selma — Inspeção de OS", page_icon="⚡", layout="centered")


# --------------------------------------------------------------------------
# Estilo (visual estilo WhatsApp)
# --------------------------------------------------------------------------
def inject_css() -> None:
    st.markdown(
        """
        <style>
        .wa-chat {
            background:#0b141a; border-radius:12px; padding:14px;
            min-height:240px; max-height:60vh; overflow-y:auto;
            display:flex; flex-direction:column; gap:6px;
            background-image:linear-gradient(rgba(11,20,26,.96),rgba(11,20,26,.96));
        }
        .wa-row { display:flex; }
        .wa-row.bot { justify-content:flex-start; }
        .wa-row.user { justify-content:flex-end; }
        .wa-bubble {
            max-width:78%; padding:8px 12px; border-radius:10px;
            font-size:0.95rem; line-height:1.35; color:#e9edef; white-space:pre-wrap;
            box-shadow:0 1px 1px rgba(0,0,0,.2);
        }
        .wa-bubble.bot { background:#202c33; border-top-left-radius:2px; }
        .wa-bubble.user { background:#005c4b; border-top-right-radius:2px; }
        .wa-header {
            background:#202c33; color:#e9edef; padding:10px 14px;
            border-radius:12px 12px 0 0; font-weight:600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------
def init_state() -> None:
    d = {
        "stage": "login",
        "phone": "",
        "technical": None,
        "orders": [],
        "os_number": None,
        "service_order_id": None,
        "step_idx": 0,
        "responses": [],        # [{step_idx, step_key, qkey, var, qtype, label, value, options}]
        "transcript": [],       # [{role, text}]
        "shown_intro": set(),
        "pending_prompt": None,
        "report": None,
        "save_error": None,
        "report_error": None,
        "draft_token": None,
        "draft_loaded": False,
    }
    for k, v in d.items():
        st.session_state.setdefault(k, v)


def recs_for(step_idx: int) -> list[dict]:
    return [r for r in st.session_state.responses if r["step_idx"] == step_idx]


# --------------------------------------------------------------------------
# Salvamento (mapeia respostas -> colunas, replicando os webhooks do Typebot)
# --------------------------------------------------------------------------
def build_save_data(step: flow.Step, vals: dict) -> dict | None:
    part = get_part(step.key)
    if step.key == "capacitor_bank":
        c = vals.get("_bank_count")
        if c is None or "0" in str(c):
            return None  # banco inexistente -> não salva (igual ao pulo do Typebot)
    if step.key == "additional_services_executed":
        if not (vals.get("description") or "").strip():
            return None

    data = {col: vals[col] for col in part.columns
            if vals.get(col) not in (None, "")}

    if step.key == "capacitor_bank" and flow.parse_cap_count(vals.get("_cap_count")) > 0:
        data["cells_measurements_data"] = flow.build_capacitors_json(vals)

    if step.key == "general_conditions":
        rg = vals.get("rubber_gloves_hv_status")
        if rg:
            data["rubber_mat_status"] = rg
    if step.key == "general_observations":
        ov = vals.get("oil_volume")
        if ov:
            data["oil_collection_reason"] = ov

    return data or None


# --------------------------------------------------------------------------
# Telas
# --------------------------------------------------------------------------
def render_transcript() -> None:
    rows = []
    for m in st.session_state.transcript:
        role = "user" if m["role"] == "user" else "bot"
        rows.append(
            f'<div class="wa-row {role}"><div class="wa-bubble {role}">'
            f'{html.escape(m["text"])}</div></div>'
        )
    st.markdown(f'<div class="wa-chat">{"".join(rows)}</div>', unsafe_allow_html=True)
    # Auto-scroll: rola o container do chat até a última mensagem.
    components.html(
        f"""
        <script>
            const n = {len(st.session_state.transcript)};
            const doc = window.parent.document;
            const scroll = () => {{
                const els = doc.querySelectorAll('.wa-chat');
                const el = els[els.length - 1];
                if (el) el.scrollTop = el.scrollHeight;
            }};
            scroll();
            setTimeout(scroll, 60);
            setTimeout(scroll, 200);
        </script>
        """,
        height=0,
    )


def render_login() -> None:
    st.markdown('<div class="wa-header">⚡ Selma — Assistente de OS</div>', unsafe_allow_html=True)
    st.write("Olá, eu sou a **Selma**! Vou te ajudar na OS de hoje. 🫡")
    faltando = config.missing_db_config()
    if faltando:
        st.error("Configuração ausente no .env: " + ", ".join(faltando))
        return
    phone = st.text_input("Informe seu número de telefone", value=st.session_state.phone,
                          placeholder="(11) 99999-9999")
    if st.button("Entrar", type="primary"):
        st.session_state.phone = phone
        try:
            tech = db.find_technical_by_phone(phone)
        except Exception as e:  # noqa: BLE001
            st.error(f"Erro ao consultar o banco: {e}")
            return
        if not tech:
            st.error("Nenhuma OS cadastrada nesse número. "
                     "Procure o supervisor para realizar o cadastro.")
            return
        orders = db.list_active_orders(tech["id"])
        if not orders:
            st.error("Nenhuma OS cadastrada nesse número. "
                     "Procure o supervisor para realizar o cadastro.")
            return
        st.session_state.technical = tech
        st.session_state.orders = orders
        st.session_state.stage = "pick_os"
        st.rerun()


def render_pick_os() -> None:
    tech = st.session_state.technical
    st.markdown('<div class="wa-header">⚡ Selma — Selecione a OS</div>', unsafe_allow_html=True)
    st.write(f"Olá, **{tech.get('name') or 'técnico'}**! "
             "Verifiquei que você possui estas OS em aberto. Com qual deseja continuar?")
    for o in st.session_state.orders:
        label = f"OS {o['os_number']}"
        if o.get("client_name"):
            label += f" — {o['client_name']}"
        label += f"  ·  {int(round(o['progress'] * 100))}% concluído"
        if st.button(label, key=f"os_{o['os_number']}"):
            sid = db.resolve_service_order_id(o["os_number"])
            st.session_state.os_number = o["os_number"]
            st.session_state.service_order_id = sid
            st.session_state.step_idx = 0
            st.session_state.responses = []
            st.session_state.transcript = [
                {"role": "bot",
                 "text": f"Ótimo! Vamos preencher a OS {o['os_number']}. "
                         "Responda cada item abaixo. 👇"}
            ]
            st.session_state.shown_intro = set()
            st.session_state.pending_prompt = None
            st.session_state.stage = "chat"
            st.rerun()
    if st.button("⬅ Voltar"):
        st.session_state.stage = "login"
        st.rerun()


def record_answer(step_idx: int, step_key: str, q: flow.Question, value: str) -> None:
    st.session_state.responses.append({
        "step_idx": step_idx,
        "step_key": step_key,
        "qkey": q.qkey,
        "var": q.var,
        "qtype": q.qtype,
        "label": q.text,
        "value": value,
        "options": q.options,
    })
    st.session_state.transcript.append({"role": "user", "text": value})
    st.session_state.pending_prompt = None
    st.rerun()


def render_chat() -> None:
    # Avança até uma etapa com pergunta pendente.
    while st.session_state.step_idx < len(flow.STEPS):
        step = flow.STEPS[st.session_state.step_idx]
        q = flow.next_question(step, recs_for(st.session_state.step_idx))
        if q is None:
            st.session_state.step_idx += 1
            continue
        break

    if st.session_state.step_idx >= len(flow.STEPS):
        st.session_state.stage = "review"
        st.rerun()

    idx = st.session_state.step_idx
    step = flow.STEPS[idx]
    q = flow.next_question(step, recs_for(idx))

    # Intro da etapa (uma vez).
    if idx not in st.session_state.shown_intro:
        st.session_state.transcript.append(
            {"role": "bot", "text": f"{step.title}\n\n{_plain(step.intro)}"})
        st.session_state.shown_intro.add(idx)

    # Prompt da pergunta atual (uma vez).
    scoped = f"{idx}:{q.qkey}"
    if st.session_state.pending_prompt != scoped:
        if q.section:
            st.session_state.transcript.append({"role": "bot", "text": q.section})
        st.session_state.transcript.append({"role": "bot", "text": q.text})
        st.session_state.pending_prompt = scoped

    st.markdown(f'<div class="wa-header">⚡ Selma · OS {st.session_state.os_number} · {step.title}'
                f'</div>', unsafe_allow_html=True)
    render_transcript()

    total = len(flow.STEPS)
    st.progress((idx) / total, text=f"Etapa {idx + 1} de {total}")

    if q.qtype == "choice":
        cols = st.columns(len(q.options))
        for i, opt in enumerate(q.options):
            if cols[i].button(opt, key=f"opt_{scoped}_{i}", use_container_width=True):
                record_answer(idx, step.key, q, opt)
    else:
        val = st.chat_input("Digite sua resposta...")
        if val is not None and str(val).strip() != "":
            record_answer(idx, step.key, q, str(val).strip())


def _plain(text: str) -> str:
    return text.replace("*", "")


def _display_records(step_idx: int) -> list[dict]:
    """Recs da etapa, colapsando 'Descreva a situação' sobre a escolha (mesma var)."""
    recs = recs_for(step_idx)
    last_idx_by_var: dict[str, int] = {}
    for i, r in enumerate(recs):
        last_idx_by_var[r["var"]] = i
    return [r for i, r in enumerate(recs) if last_idx_by_var[r["var"]] == i]


def render_review() -> None:
    st.markdown('<div class="wa-header">📝 Revisão das respostas</div>', unsafe_allow_html=True)
    st.write("Confira e edite as respostas abaixo. Se estiver tudo certo, "
             "clique em **Confirmar e salvar**.")

    if st.session_state.save_error:
        st.error(st.session_state.save_error)

    with st.form("review_form"):
        for idx, step in enumerate(flow.STEPS):
            recs = _display_records(idx)
            if not recs:
                continue
            st.subheader(step.title)
            for r in recs:
                wkey = f"edit_{idx}_{r['qkey']}"
                if r["qtype"] == "choice" and r["options"] and r["value"] in r["options"]:
                    st.selectbox(r["label"], r["options"],
                                 index=r["options"].index(r["value"]), key=wkey)
                else:
                    st.text_input(r["label"], value=str(r["value"]), key=wkey)
        submitted = st.form_submit_button("✅ Confirmar e salvar", type="primary")

    if st.button("⬅ Voltar ao chat"):
        st.session_state.stage = "chat"
        st.rerun()

    if submitted:
        _apply_edits()
        _save_and_generate()


def _apply_edits() -> None:
    for idx, step in enumerate(flow.STEPS):
        for r in _display_records(idx):
            wkey = f"edit_{idx}_{r['qkey']}"
            if wkey in st.session_state:
                r["value"] = st.session_state[wkey]


def _save_and_generate() -> None:
    st.session_state.save_error = None
    st.session_state.report_error = None
    os_number = st.session_state.os_number
    sid = st.session_state.service_order_id

    # 1. Salvamento no banco — se falhar aqui, mantém o usuário na revisão.
    try:
        with st.spinner("Salvando respostas no banco..."):
            for idx, step in enumerate(flow.STEPS):
                recs = recs_for(idx)
                if not recs:
                    continue
                vals = flow.derive_vals(recs)
                data = build_save_data(step, vals)
                if data is None:
                    continue
                db.save_checklist_part(os_number, step.key, data,
                                       instance=step.instance, mark_complete=True)
            db.apply_progress(sid, recompute=True)
            if st.session_state.draft_token:
                try:
                    drafts.mark_saved(st.session_state.draft_token)
                except Exception:  # noqa: BLE001 - não bloquear por causa do status
                    pass
    except Exception as e:  # noqa: BLE001
        st.session_state.save_error = f"Falha ao salvar no banco: {e}"
        st.rerun()
        return

    # 2. Relatório — os dados JÁ foram salvos; uma falha aqui não os perde.
    try:
        with st.spinner("Gerando o relatório com a IA (Groq)..."):
            st.session_state.report = report_mod.generate_full_report(os_number, sid)
    except Exception as e:  # noqa: BLE001
        st.session_state.report = None
        st.session_state.report_error = (
            f"As respostas foram salvas com sucesso, mas houve uma falha ao gerar "
            f"o relatório: {e}"
        )

    st.session_state.stage = "report"
    st.rerun()


REPORT_LABELS = [
    ("entrada_alimentacao", "Entrada de Alimentação"),
    ("quadro_protecao_geral", "Quadro de Proteção Geral / Proteção de Média Tensão"),
    ("transformador", "Transformador"),
    ("quadro_geral_baixa_tensao", "Quadro Geral de Baixa Tensão (QGBT)"),
    ("banco_capacitores", "Banco de Capacitores"),
    ("servicos_realizados", "Serviços Realizados"),
    ("recomendacoes", "Recomendações"),
]


def render_report() -> None:
    rep = st.session_state.report or {}
    st.markdown('<div class="wa-header">📄 Relatório técnico da OS '
                f'{st.session_state.os_number}</div>', unsafe_allow_html=True)

    if st.session_state.report_error:
        st.warning(st.session_state.report_error)
        if st.button("🔄 Tentar gerar o relatório novamente"):
            try:
                with st.spinner("Gerando o relatório com a IA (Groq)..."):
                    st.session_state.report = report_mod.generate_full_report(
                        st.session_state.os_number, st.session_state.service_order_id)
                st.session_state.report_error = None
            except Exception as e:  # noqa: BLE001
                st.session_state.report_error = f"Ainda houve falha ao gerar o relatório: {e}"
            st.rerun()
    else:
        st.success("Todos os dados foram registrados e o relatório foi gerado com sucesso! "
                   "Até o próximo serviço 🫡😉😎")

    if rep:
        for col, label in REPORT_LABELS:
            st.subheader(label)
            st.write(rep.get(col) or "_(sem conteúdo)_")

    if st.button("🏠 Nova OS"):
        try:
            st.query_params.clear()
        except Exception:  # noqa: BLE001
            pass
        for k in ("stage", "os_number", "service_order_id", "step_idx", "responses",
                  "transcript", "shown_intro", "pending_prompt", "report",
                  "save_error", "report_error", "draft_token", "draft_loaded"):
            st.session_state.pop(k, None)
        st.rerun()


def load_draft_if_present() -> None:
    """Se a URL tiver ?draft=<token>, carrega o rascunho e vai direto à revisão."""
    if st.session_state.draft_loaded:
        return
    token = st.query_params.get("draft")
    if not token:
        return
    st.session_state.draft_loaded = True  # evita recarregar a cada rerun
    try:
        draft = drafts.get_draft(token)
    except Exception as e:  # noqa: BLE001
        st.session_state.save_error = f"Não consegui carregar o rascunho: {e}"
        return
    if not draft:
        st.session_state.save_error = "Rascunho não encontrado ou expirado."
        return
    st.session_state.draft_token = token
    st.session_state.os_number = draft.get("os_number")
    st.session_state.service_order_id = draft.get("service_order_id")
    st.session_state.responses = draft.get("answers") or []
    st.session_state.stage = "review"


# --------------------------------------------------------------------------
def main() -> None:
    inject_css()
    init_state()
    load_draft_if_present()
    stage = st.session_state.stage
    if stage == "login":
        render_login()
    elif stage == "pick_os":
        render_pick_os()
    elif stage == "chat":
        render_chat()
    elif stage == "review":
        render_review()
    elif stage == "report":
        render_report()


main()
