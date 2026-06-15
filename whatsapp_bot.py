"""Bot do WhatsApp (via Evolution API) que conduz o preenchimento da inspeção.

Reaproveita o MESMO motor de fluxo (`selma/flow.py`) e o acesso ao banco
(`selma/db.py`) usados pelo bot do Telegram (`bot.py`) — sem tocar naquele.
Diferenças do WhatsApp: não há botões inline; as perguntas de múltipla escolha
são enviadas como lista numerada e o usuário responde com o número da opção. O
técnico é identificado automaticamente pelo número do remetente.

Arquitetura: servidor Flask que recebe o webhook da Evolution API (evento
`messages.upsert`) e responde enviando mensagens via API da Evolution
(`/message/sendText/{instance}`). O estado de cada conversa fica em memória,
indexado pelo remoteJid (chatId).

Rodar:  python whatsapp_bot.py
Apontar o webhook da Evolution para:  http://<host>:<WHATSAPP_BOT_PORT>/webhook
"""
import json
import logging
import re

import requests
from flask import Flask, jsonify, request

from selma import config, db, drafts, flow

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("selma-whatsapp-bot")

app = Flask(__name__)

SUPERVISOR_MSG = (
    "Nenhuma OS cadastrada nesse número. Procure o supervisor para realizar o cadastro."
)

# Estado por conversa (chatId -> dict), espelhando context.user_data do Telegram.
SESSIONS: dict[str, dict] = {}


# --------------------------------------------------------------------------
# Envio de mensagens via Evolution API
# --------------------------------------------------------------------------
def send_text(chat_id: str, text: str) -> None:
    headers = {"Content-Type": "application/json"}
    if config.EVOLUTION_API_KEY:
        headers["apikey"] = config.EVOLUTION_API_KEY
    try:
        res = requests.post(
            f"{config.EVOLUTION_URL}/message/sendText/{config.EVOLUTION_INSTANCE}",
            headers=headers,
            json={"number": chat_id, "text": text},
            timeout=30,
        )
        if not res.ok:
            logger.error("Falha ao enviar mensagem Evolution %s: %s", res.status_code, res.text[:300])
    except Exception:  # noqa: BLE001
        logger.exception("erro ao enviar mensagem via Evolution")


def _plain(text: str) -> str:
    """Remove marcação Markdown (* ) usada nos textos do fluxo."""
    return text.replace("*", "")


# --------------------------------------------------------------------------
# Motor de perguntas (espelha bot.py, adaptado para texto puro)
# --------------------------------------------------------------------------
def _record_answer(sess: dict, value: str) -> None:
    cur = sess["cur_q"]
    sess["records"].append({
        "step_idx": cur["step_idx"],
        "step_key": cur["step_key"],
        "qkey": cur["qkey"],
        "var": cur["var"],
        "qtype": cur["qtype"],
        "label": cur["label"],
        "value": value,
        "options": cur["options"],
    })
    sess["awaiting"] = None


def send_next_question(chat_id: str, sess: dict) -> None:
    idx, q = flow.current_step_and_question(sess["records"], sess["step_idx"])
    sess["step_idx"] = idx

    if q is None:
        finalize(chat_id, sess)
        return

    step = flow.STEPS[idx]

    # Intro da etapa (uma vez por etapa).
    if idx not in sess["shown_intro"]:
        send_text(chat_id,
                  f"{step.title} — etapa {idx + 1} de {len(flow.STEPS)}\n\n{_plain(step.intro)}")
        sess["shown_intro"].add(idx)

    if q.section:
        send_text(chat_id, q.section)

    sess["cur_q"] = {
        "qkey": q.qkey, "var": q.var, "qtype": q.qtype,
        "label": q.text, "options": q.options, "step_idx": idx, "step_key": step.key,
    }

    if q.qtype == "choice":
        sess["awaiting"] = "choice"
        lines = [q.text, ""]
        for i, opt in enumerate(q.options, start=1):
            lines.append(f"{i}) {opt}")
        lines.append("\nResponda com o número da opção.")
        send_text(chat_id, "\n".join(lines))
    else:
        sess["awaiting"] = "text"
        send_text(chat_id, q.text)


def handle_choice(chat_id: str, sess: dict, text: str) -> None:
    options = sess["cur_q"]["options"] or []
    choice = text.strip()
    idx = None
    if choice.isdigit():
        n = int(choice)
        if 1 <= n <= len(options):
            idx = n - 1
    if idx is None:
        # Aceita também o texto exato da opção (case-insensitive).
        for i, opt in enumerate(options):
            if opt.lower() == choice.lower():
                idx = i
                break
    if idx is None:
        send_text(chat_id, "Opção inválida. Responda com o número correspondente.")
        return
    _record_answer(sess, options[idx])
    send_next_question(chat_id, sess)


def handle_text_answer(chat_id: str, sess: dict, text: str) -> None:
    _record_answer(sess, text.strip())
    send_next_question(chat_id, sess)


# --------------------------------------------------------------------------
# Início / identificação
# --------------------------------------------------------------------------
def start_session(chat_id: str, phone: str) -> None:
    try:
        tech = db.find_technical_by_phone(phone)
    except Exception as e:  # noqa: BLE001
        logger.exception("erro ao buscar técnico")
        send_text(chat_id, f"Erro ao consultar o banco: {e}")
        return

    if not tech:
        send_text(chat_id, SUPERVISOR_MSG)
        return

    orders = db.list_active_orders(tech["id"])
    if not orders:
        send_text(chat_id, SUPERVISOR_MSG)
        return

    SESSIONS[chat_id] = {
        "technical": tech,
        "orders": {str(i + 1): o for i, o in enumerate(orders)},
        "awaiting": "pick_os",
        "records": [],
        "step_idx": 0,
        "shown_intro": set(),
        "cur_q": None,
        "os_number": None,
        "service_order_id": None,
    }

    lines = [
        f"Olá, {tech.get('name') or 'técnico'}! Eu sou a *Selma* e vou te ajudar na OS de hoje. ⚡".replace("*", ""),
        "",
        "Estas são suas OS em aberto. Responda com o número da que deseja continuar:",
        "",
    ]
    for i, o in enumerate(orders, start=1):
        label = f"{i}) OS {o['os_number']}"
        if o.get("client_name"):
            label += f" — {o['client_name']}"
        lines.append(label)
    send_text(chat_id, "\n".join(lines))


def handle_pick_os(chat_id: str, sess: dict, text: str) -> None:
    o = sess["orders"].get(text.strip())
    if not o:
        send_text(chat_id, "Opção inválida. Responda com o número da OS desejada.")
        return
    os_number = o["os_number"]
    try:
        sid = db.resolve_service_order_id(os_number)
    except Exception as e:  # noqa: BLE001
        send_text(chat_id, f"Erro ao abrir a OS: {e}")
        return

    sess["os_number"] = os_number
    sess["service_order_id"] = sid
    sess["records"] = []
    sess["step_idx"] = 0
    sess["shown_intro"] = set()
    sess["awaiting"] = None
    send_text(chat_id, f"Ótimo! Vamos preencher a OS {os_number}. 👇")
    send_next_question(chat_id, sess)


# --------------------------------------------------------------------------
# Finalização -> rascunho + link
# --------------------------------------------------------------------------
def finalize(chat_id: str, sess: dict) -> None:
    try:
        token = drafts.create_draft(
            os_number=sess["os_number"],
            service_order_id=sess.get("service_order_id"),
            technical=sess.get("technical"),
            answers=sess["records"],
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("erro ao criar rascunho")
        send_text(chat_id, f"Não consegui salvar o rascunho: {e}")
        return

    link = f"{config.STREAMLIT_APP_URL}?draft={token}"
    send_text(
        chat_id,
        "✅ Você concluiu todas as perguntas!\n\n"
        "Abra o link abaixo para revisar e editar as respostas. Quando estiver tudo "
        "certo, confirme para salvar e gerar o relatório:\n\n" + link,
    )
    SESSIONS.pop(chat_id, None)


# --------------------------------------------------------------------------
# Webhook
# --------------------------------------------------------------------------
def _phone_from_chat_id(chat_id: str) -> str:
    return chat_id.split("@", 1)[0]


def _only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def extract_phone(data: dict, chat_id: str) -> str:
    """Resolve o telefone real do remetente a partir do `data` do messages.upsert.

    O remoteJid individual costuma vir como `5511...@s.whatsapp.net` (o número está
    embutido), mas pode vir como `@lid` (id oculto, NÃO é telefone). Nesse caso
    procuramos o número em campos alternativos da Evolution. Loga cada candidato
    considerado e o escolhido para diagnóstico interno.
    """
    key = data.get("key") or {}
    candidates: list[tuple[str, str | None]] = [
        ("key.senderPn", key.get("senderPn")),
        ("key.remoteJidAlt", key.get("remoteJidAlt")),
        ("key.participant", key.get("participant")),
    ]
    frm = key.get("remoteJid") or chat_id
    if frm.endswith("@s.whatsapp.net") or frm.endswith("@c.us"):
        candidates.append(("remoteJid", frm))

    for source, raw in candidates:
        phone = _only_digits(raw)
        logger.info("extract_phone: candidato %s=%r -> %r", source, raw, phone)
        if phone:
            logger.info("extract_phone: telefone escolhido=%s (via %s)", phone, source)
            return phone

    fallback = _only_digits(_phone_from_chat_id(frm))
    if frm.endswith("@lid"):
        logger.warning(
            "extract_phone: 'remoteJid'=%s é @lid e nenhum telefone foi resolvido; "
            "usando fallback=%s (pode falhar na identificação do técnico)", frm, fallback)
    else:
        logger.info("extract_phone: usando fallback do chatId=%s", fallback)
    return fallback


def route_message(chat_id: str, text: str, phone: str) -> None:
    sess = SESSIONS.get(chat_id)
    cmd = text.strip().lower()

    # Reinício explícito ou primeira interação.
    if sess is None or cmd in ("/start", "oi", "olá", "ola", "menu"):
        start_session(chat_id, phone)
        return

    awaiting = sess.get("awaiting")
    if awaiting == "pick_os":
        handle_pick_os(chat_id, sess, text)
    elif awaiting == "choice":
        handle_choice(chat_id, sess, text)
    elif awaiting == "text":
        handle_text_answer(chat_id, sess, text)
    else:
        send_text(chat_id, "Envie *oi* para iniciar o preenchimento de uma OS.".replace("*", ""))


def _extract_text(message: dict) -> str | None:
    """Texto de uma mensagem da Evolution (conversation ou extendedTextMessage)."""
    if not isinstance(message, dict):
        return None
    conv = message.get("conversation")
    if isinstance(conv, str):
        return conv
    ext = message.get("extendedTextMessage") or {}
    txt = ext.get("text")
    return txt if isinstance(txt, str) else None


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True) or {}
    logger.info("Evolution payload: %s", json.dumps(body, ensure_ascii=False, default=str))
    # A Evolution envia o evento em minúsculas com ponto (ex.: "messages.upsert").
    if (body.get("event") or "").lower() not in ("messages.upsert", "messages_upsert"):
        return jsonify({"status": "ignored"})

    data = body.get("data") or {}
    # Quando vem em lote, `data` pode ser uma lista; pega a primeira mensagem.
    if isinstance(data, list):
        data = data[0] if data else {}
    key = data.get("key") or {}
    if key.get("fromMe"):
        return jsonify({"status": "ignored"})

    chat_id = key.get("remoteJid")
    text = _extract_text(data.get("message") or {})
    if not chat_id or not isinstance(text, str) or not text.strip():
        return jsonify({"status": "ignored"})

    # Ignora grupos (chatId de grupo termina em @g.us).
    if chat_id.endswith("@g.us"):
        return jsonify({"status": "ignored"})

    phone = extract_phone(data, chat_id)

    try:
        route_message(chat_id, text, phone)
    except Exception:  # noqa: BLE001
        logger.exception("erro ao processar mensagem")
        send_text(chat_id, "Ops! Tive um problema ao processar sua mensagem. Envie *oi* para recomeçar.".replace("*", ""))
    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# --------------------------------------------------------------------------
def main() -> None:
    if config.missing_db_config():
        raise SystemExit("Faltam variáveis do banco no .env: "
                         + ", ".join(config.missing_db_config()))
    if not config.EVOLUTION_URL:
        raise SystemExit("EVOLUTION_URL não configurado no .env")

    logger.info("Bot WhatsApp iniciado. EVOLUTION_URL=%s instância=%s porta=%s",
                config.EVOLUTION_URL, config.EVOLUTION_INSTANCE, config.WHATSAPP_BOT_PORT)
    app.run(host="0.0.0.0", port=config.WHATSAPP_BOT_PORT)


if __name__ == "__main__":
    main()
