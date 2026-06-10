"""Bot do Telegram (long polling) que conduz o preenchimento da inspeção.

Reaproveita o motor de fluxo (`selma/flow.py`) e o acesso ao banco
(`selma/db.py`). Ao terminar todas as perguntas, grava um rascunho
(`inspection_draft`) e envia ao técnico um link para o formulário editável
hospedado no Streamlit (`STREAMLIT_APP_URL?draft=<token>`).

Rodar:  python bot.py
"""
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from selma import config, db, drafts, flow

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("selma-bot")

SUPERVISOR_MSG = (
    "Nenhuma OS cadastrada nesse número. Procure o supervisor para realizar o cadastro."
)


# --------------------------------------------------------------------------
# Início / identificação
# --------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Compartilhar meu contato", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await update.message.reply_text(
        "Olá! Eu sou a *Selma* e vou te ajudar na OS de hoje. ⚡\n\n"
        "Para começar, compartilhe seu contato no botão abaixo.",
        parse_mode="Markdown", reply_markup=keyboard,
    )


async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    phone = update.message.contact.phone_number
    try:
        tech = db.find_technical_by_phone(phone)
    except Exception as e:  # noqa: BLE001
        logger.exception("erro ao buscar técnico")
        await update.message.reply_text(f"Erro ao consultar o banco: {e}")
        return

    if not tech:
        await update.message.reply_text(SUPERVISOR_MSG, reply_markup=ReplyKeyboardRemove())
        return

    orders = db.list_active_orders(tech["id"])
    if not orders:
        await update.message.reply_text(SUPERVISOR_MSG, reply_markup=ReplyKeyboardRemove())
        return

    context.user_data["technical"] = tech
    context.user_data["orders"] = {str(o["os_number"]): o for o in orders}

    buttons = []
    for o in orders:
        label = f"OS {o['os_number']}"
        if o.get("client_name"):
            label += f" — {o['client_name']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"os:{o['os_number']}")])

    await update.message.reply_text(
        f"Olá, *{tech.get('name') or 'técnico'}*! "
        "Estas são suas OS em aberto. Com qual deseja continuar?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def on_pick_os(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    os_number = int(query.data.split(":", 1)[1])
    try:
        sid = db.resolve_service_order_id(os_number)
    except Exception as e:  # noqa: BLE001
        await query.edit_message_text(f"Erro ao abrir a OS: {e}")
        return

    context.user_data["os_number"] = os_number
    context.user_data["service_order_id"] = sid
    context.user_data["records"] = []
    context.user_data["step_idx"] = 0
    context.user_data["shown_intro"] = set()

    await query.edit_message_text(f"Ótimo! Vamos preencher a OS {os_number}. 👇")
    await send_next_question(query.message, context)


# --------------------------------------------------------------------------
# Motor de perguntas
# --------------------------------------------------------------------------
async def send_next_question(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    records = context.user_data["records"]
    idx, q = flow.current_step_and_question(records, context.user_data["step_idx"])
    context.user_data["step_idx"] = idx

    if q is None:
        await finalize(message, context)
        return

    step = flow.STEPS[idx]

    # Intro da etapa (uma vez por etapa).
    shown = context.user_data["shown_intro"]
    if idx not in shown:
        await message.reply_text(
            f"*{step.title}* — etapa {idx + 1} de {len(flow.STEPS)}\n\n{step.intro}",
            parse_mode="Markdown",
        )
        shown.add(idx)

    if q.section:
        await message.reply_text(q.section)

    context.user_data["cur_q"] = {
        "qkey": q.qkey, "var": q.var, "qtype": q.qtype,
        "label": q.text, "options": q.options, "step_idx": idx, "step_key": step.key,
    }

    if q.qtype == "choice":
        context.user_data["awaiting"] = "choice"
        buttons = [
            [InlineKeyboardButton(opt, callback_data=f"a:{i}")]
            for i, opt in enumerate(q.options)
        ]
        await message.reply_text(q.text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        context.user_data["awaiting"] = "text"
        await message.reply_text(q.text)


def _record_answer(context: ContextTypes.DEFAULT_TYPE, value: str) -> None:
    cur = context.user_data["cur_q"]
    context.user_data["records"].append({
        "step_idx": cur["step_idx"],
        "step_key": cur["step_key"],
        "qkey": cur["qkey"],
        "var": cur["var"],
        "qtype": cur["qtype"],
        "label": cur["label"],
        "value": value,
        "options": cur["options"],
    })
    context.user_data["awaiting"] = None


async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if context.user_data.get("awaiting") != "choice" or "cur_q" not in context.user_data:
        return
    i = int(query.data.split(":", 1)[1])
    options = context.user_data["cur_q"]["options"] or []
    if i >= len(options):
        return
    value = options[i]
    # Mantém o histórico: troca os botões pela resposta escolhida.
    await query.edit_message_text(f"{context.user_data['cur_q']['label']}\n→ *{value}*",
                                  parse_mode="Markdown")
    _record_answer(context, value)
    await send_next_question(query.message, context)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("awaiting") != "text":
        # Fora de um fluxo ativo: orienta o usuário.
        await update.message.reply_text("Envie /start para iniciar o preenchimento de uma OS.")
        return
    _record_answer(context, update.message.text.strip())
    await send_next_question(update.message, context)


# --------------------------------------------------------------------------
# Finalização -> rascunho + link
# --------------------------------------------------------------------------
async def finalize(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        token = drafts.create_draft(
            os_number=context.user_data["os_number"],
            service_order_id=context.user_data.get("service_order_id"),
            technical=context.user_data.get("technical"),
            answers=context.user_data["records"],
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("erro ao criar rascunho")
        await message.reply_text(f"Não consegui salvar o rascunho: {e}")
        return

    link = f"{config.STREAMLIT_APP_URL}?draft={token}"
    await message.reply_text(
        "✅ Você concluiu todas as perguntas!\n\n"
        "Toque no botão abaixo para *revisar e editar* as respostas. "
        "Quando estiver tudo certo, confirme para salvar e gerar o relatório.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📝 Abrir formulário para revisar e salvar", url=link)]]
        ),
    )
    context.user_data["awaiting"] = None


# --------------------------------------------------------------------------
def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN não configurado no .env")
    if config.missing_db_config():
        raise SystemExit("Faltam variáveis do banco no .env: "
                         + ", ".join(config.missing_db_config()))

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, on_contact))
    app.add_handler(CallbackQueryHandler(on_pick_os, pattern=r"^os:"))
    app.add_handler(CallbackQueryHandler(on_choice, pattern=r"^a:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Bot iniciado (long polling). STREAMLIT_APP_URL=%s", config.STREAMLIT_APP_URL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
