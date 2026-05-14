from __future__ import annotations

import logging
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from chamaleon.config import Settings
from chamaleon.domain.types import TransactionDraft
from chamaleon.infra.ai import ReportAIClient
from chamaleon.infra.db import Database
from chamaleon.infra.email import EmailClient, EmailDeliveryError
from chamaleon.infra.logging import configure_logging
from chamaleon.repos.reports import ReportRepository
from chamaleon.repos.transactions import TransactionRepository
from chamaleon.repos.users import UserRepository
from chamaleon.services.finance import FinanceService
from chamaleon.services.parser import detect_intent, normalize_amount, parse_transaction_text
from chamaleon.services.reports import ReportService


logger = logging.getLogger(__name__)

STATE_AWAITING_EMAIL = "awaiting_email"
STATE_AWAITING_ONBOARDING_SALARY = "awaiting_onboarding_salary"
STATE_AWAITING_SALARY_UPDATE = "awaiting_salary_update"
STATE_AWAITING_TRANSACTION = "awaiting_transaction"
STATE_AWAITING_TRANSACTION_CONFIRM = "awaiting_transaction_confirm"


class BotRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings)
        self.users = UserRepository()
        self.transactions = TransactionRepository()
        self.reports = ReportRepository()
        self.finance = FinanceService(self.transactions)
        self.report_service = ReportService(
            settings=settings,
            finance_service=self.finance,
            report_repository=self.reports,
            ai_client=ReportAIClient(settings),
            email_client=EmailClient(settings),
        )

    def get_user(self, session, update: Update):
        return self.users.get_by_telegram_id(session, str(update.effective_user.id))


def _menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Novo registro", callback_data="menu:new")],
            [InlineKeyboardButton("Historico", callback_data="menu:history")],
            [InlineKeyboardButton("Meu dinheiro", callback_data="menu:summary")],
            [InlineKeyboardButton("Relatorio", callback_data="menu:report")],
            [InlineKeyboardButton("Excluir transacao", callback_data="menu:delete")],
        ]
    )


def _format_amount(amount: Decimal) -> str:
    return f"R$ {amount:.2f}".replace(".", ",")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    with runtime.db.session() as session:
        user = runtime.get_user(session, update)
        if user is None:
            context.user_data["state"] = STATE_AWAITING_EMAIL
            await update.message.reply_text("Vamos configurar seu ChamaLeon. Qual e o seu e-mail?")
            return
    await update.message.reply_text(
        "ChamaLeon pronto. Pode me mandar uma mensagem natural ou usar o menu.",
        reply_markup=_menu_markup(),
    )


async def command_registro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        raw_text = " ".join(context.args)
        await _handle_transaction_candidate(update, context, raw_text)
        return
    context.user_data["state"] = STATE_AWAITING_TRANSACTION
    await update.message.reply_text(
        "Me diga a transacao no seu jeito. Ex.: 'gastei 39 no ifood' ou 'recebi 1200 de freelance'."
    )


async def command_historico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_history(update, context, as_edit=False)


async def command_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_summary(update, context, as_edit=False)


async def command_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_report(update, context, as_edit=False)


async def _handle_transaction_candidate(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    draft = parse_transaction_text(text)
    if draft is None:
        await update.effective_message.reply_text(
            "Nao consegui entender essa transacao. Tente algo como 'gastei 42 no ifood' ou '/registro uber 25'."
        )
        return
    context.user_data["pending_transaction"] = draft
    context.user_data["state"] = STATE_AWAITING_TRANSACTION_CONFIRM
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirmar", callback_data="tx:confirm"),
                InlineKeyboardButton("Cancelar", callback_data="tx:cancel"),
            ]
        ]
    )
    await update.effective_message.reply_text(_format_draft_preview(draft), reply_markup=keyboard)


def _format_draft_preview(draft: TransactionDraft) -> str:
    tx_type = "Receita" if draft.transaction_type == "income" else "Gasto"
    details = f"\nObs: {draft.details}" if draft.details else ""
    return (
        "Confirma esta transacao?\n"
        f"Descricao: {draft.description}\n"
        f"Valor: {_format_amount(draft.amount)}\n"
        f"Categoria: {draft.category}\n"
        f"Tipo: {tx_type}\n"
        f"Data: {draft.transaction_date.isoformat()}{details}"
    )


async def _confirm_pending_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, as_edit: bool = True) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    draft: TransactionDraft | None = context.user_data.get("pending_transaction")
    if draft is None:
        if as_edit:
            await update.callback_query.edit_message_text("Nenhuma transacao pendente.")
        else:
            await update.message.reply_text("Nenhuma transacao pendente.")
        return

    with runtime.db.session() as session:
        user = runtime.get_user(session, update)
        if user is None:
            message = "Finalize o onboarding com /start antes de registrar transacoes."
            if as_edit:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return
        transaction = runtime.transactions.create(session, user, draft)

    context.user_data.pop("pending_transaction", None)
    context.user_data.pop("state", None)
    message = f"Transacao registrada com sucesso. ID {transaction.id}."
    if as_edit:
        await update.callback_query.edit_message_text(message, reply_markup=_menu_markup())
    else:
        await update.message.reply_text(message, reply_markup=_menu_markup())


async def _show_history(update: Update, context: ContextTypes.DEFAULT_TYPE, as_edit: bool = True, page: int = 1) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    with runtime.db.session() as session:
        user = runtime.get_user(session, update)
        if user is None:
            message = "Use /start para finalizar seu cadastro antes de consultar historico."
            if as_edit:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return
        page_size = 5
        total = runtime.transactions.count_for_user(session, user)
        offset = max(page - 1, 0) * page_size
        items = runtime.transactions.list_recent(session, user, limit=page_size, offset=offset)

    if not items:
        message = "Nenhuma transacao registrada ainda."
    else:
        lines = [f"Historico - pagina {page}"]
        for item in items:
            sign = "+" if item.transaction_type == "income" else "-"
            lines.append(
                f"{item.id}. {item.transaction_date.isoformat()} | {item.description} | {sign}{_format_amount(item.amount)} | {item.category}"
            )
        message = "\n".join(lines)

    total_pages = max((total + 4) // 5, 1)
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("Anterior", callback_data=f"history:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Proxima", callback_data=f"history:{page + 1}"))
    keyboard_rows = [nav] if nav else []
    keyboard_rows.append([InlineKeyboardButton("Menu", callback_data="menu:home")])
    markup = InlineKeyboardMarkup(keyboard_rows)
    if as_edit:
        await update.callback_query.edit_message_text(message, reply_markup=markup)
    else:
        await update.message.reply_text(message, reply_markup=markup)


async def _show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, as_edit: bool = True) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    with runtime.db.session() as session:
        user = runtime.get_user(session, update)
        if user is None:
            message = "Use /start para concluir seu cadastro primeiro."
            if as_edit:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return
        summary = runtime.finance.build_monthly_summary(session, user)

    top_categories = "\n".join(
        [f"- {category}: {_format_amount(amount)}" for category, amount in summary.top_categories[:3]]
    ) or "- Sem gastos no periodo"
    message = (
        "Resumo do mes\n"
        f"Salario base: {_format_amount(summary.salary)}\n"
        f"Entradas: {_format_amount(summary.income_total)}\n"
        f"Gastos: {_format_amount(summary.expense_total)}\n"
        f"Saldo: {_format_amount(summary.balance)}\n\n"
        "Categorias mais pesadas:\n"
        f"{top_categories}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Atualizar salario", callback_data="menu:set_salary")],
            [InlineKeyboardButton("Menu", callback_data="menu:home")],
        ]
    )
    if as_edit:
        await update.callback_query.edit_message_text(message, reply_markup=keyboard)
    else:
        await update.message.reply_text(message, reply_markup=keyboard)


async def _prompt_salary(update: Update, context: ContextTypes.DEFAULT_TYPE, onboarding: bool = False, as_edit: bool = True) -> None:
    context.user_data["state"] = STATE_AWAITING_ONBOARDING_SALARY if onboarding else STATE_AWAITING_SALARY_UPDATE
    message = "Qual e o seu salario mensal? Ex.: 3500 ou 4500,00"
    if as_edit:
        await update.callback_query.edit_message_text(message)
    else:
        await update.effective_message.reply_text(message)


async def _send_report(update: Update, context: ContextTypes.DEFAULT_TYPE, as_edit: bool = True) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    try:
        with runtime.db.session() as session:
            user = runtime.get_user(session, update)
            if user is None:
                message = "Use /start para concluir seu cadastro primeiro."
                if as_edit:
                    await update.callback_query.edit_message_text(message)
                else:
                    await update.message.reply_text(message)
                return
            runtime.report_service.generate_and_send(session, user)
    except EmailDeliveryError as exc:
        message = f"Relatorio gerado, mas o envio por e-mail falhou: {exc}"
    except Exception as exc:
        logger.exception("Erro ao gerar relatorio")
        message = f"Nao consegui gerar o relatorio agora: {exc}"
    else:
        message = "Relatorio gerado e enviado para o e-mail cadastrado."

    if as_edit:
        await update.callback_query.edit_message_text(message, reply_markup=_menu_markup())
    else:
        await update.message.reply_text(message, reply_markup=_menu_markup())


async def _show_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, as_edit: bool = True) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    with runtime.db.session() as session:
        user = runtime.get_user(session, update)
        if user is None:
            message = "Use /start para concluir seu cadastro primeiro."
            if as_edit:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return
        items = runtime.transactions.list_recent(session, user, limit=5)

    if not items:
        text = "Nao ha transacoes para excluir."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="menu:home")]])
    else:
        rows = []
        for item in items:
            label = f"{item.id} | {item.description} | {_format_amount(item.amount)}"
            rows.append([InlineKeyboardButton(label[:64], callback_data=f"delete:{item.id}")])
        rows.append([InlineKeyboardButton("Menu", callback_data="menu:home")])
        text = "Selecione a transacao que deseja excluir."
        markup = InlineKeyboardMarkup(rows)

    if as_edit:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


async def _delete_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, transaction_id: int) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    with runtime.db.session() as session:
        user = runtime.get_user(session, update)
        deleted = False
        if user is not None:
            deleted = runtime.transactions.delete_for_user(session, user, transaction_id)
    message = "Transacao excluida." if deleted else "Nao encontrei essa transacao para o seu usuario."
    await update.callback_query.edit_message_text(message, reply_markup=_menu_markup())


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "menu:home":
        await query.edit_message_text("Menu principal", reply_markup=_menu_markup())
    elif data == "menu:new":
        context.user_data["state"] = STATE_AWAITING_TRANSACTION
        await query.edit_message_text("Mande a transacao do seu jeito. Ex.: 'gastei 39 no ifood'.")
    elif data == "menu:history":
        await _show_history(update, context, as_edit=True)
    elif data.startswith("history:"):
        await _show_history(update, context, as_edit=True, page=int(data.split(":")[1]))
    elif data == "menu:summary":
        await _show_summary(update, context, as_edit=True)
    elif data == "menu:set_salary":
        await _prompt_salary(update, context, onboarding=False, as_edit=True)
    elif data == "menu:report":
        await _send_report(update, context, as_edit=True)
    elif data == "menu:delete":
        await _show_delete_menu(update, context, as_edit=True)
    elif data.startswith("delete:"):
        await _delete_transaction(update, context, int(data.split(":")[1]))
    elif data == "tx:confirm":
        await _confirm_pending_transaction(update, context, as_edit=True)
    elif data == "tx:cancel":
        context.user_data.pop("pending_transaction", None)
        context.user_data.pop("state", None)
        await query.edit_message_text("Transacao cancelada.", reply_markup=_menu_markup())


async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime: BotRuntime = context.application.bot_data["runtime"]
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")

    if state == STATE_AWAITING_EMAIL:
        context.user_data["onboarding_email"] = text
        await _prompt_salary(update, context, onboarding=True, as_edit=False)
        return

    if state == STATE_AWAITING_ONBOARDING_SALARY:
        salary = normalize_amount(text)
        if salary is None or salary < 0:
            await update.message.reply_text("Valor invalido. Envie apenas o numero do salario.")
            return
        email = context.user_data.get("onboarding_email", "")
        with runtime.db.session() as session:
            runtime.users.create_or_update(session, str(update.effective_user.id), email, salary)
        context.user_data.clear()
        await update.message.reply_text("Cadastro concluido.", reply_markup=_menu_markup())
        return

    if state == STATE_AWAITING_SALARY_UPDATE:
        salary = normalize_amount(text)
        if salary is None or salary < 0:
            await update.message.reply_text("Valor invalido. Envie apenas o numero do salario.")
            return
        with runtime.db.session() as session:
            user = runtime.get_user(session, update)
            if user is None:
                await update.message.reply_text("Use /start antes de atualizar salario.")
                return
            runtime.users.update_salary(session, user.telegram_user_id, salary)
        context.user_data.pop("state", None)
        await update.message.reply_text("Salario atualizado.", reply_markup=_menu_markup())
        return

    if state == STATE_AWAITING_TRANSACTION:
        await _handle_transaction_candidate(update, context, text)
        return

    if state == STATE_AWAITING_TRANSACTION_CONFIRM:
        if text.lower() in {"sim", "confirmar", "ok"}:
            await _confirm_pending_transaction(update, context, as_edit=False)
            return
        if text.lower() in {"nao", "não", "cancelar"}:
            context.user_data.pop("pending_transaction", None)
            context.user_data.pop("state", None)
            await update.message.reply_text("Transacao cancelada.", reply_markup=_menu_markup())
            return

    with runtime.db.session() as session:
        user = runtime.get_user(session, update)

    if user is None:
        await update.message.reply_text("Use /start para iniciar seu cadastro.")
        return

    intent = detect_intent(text)
    if intent.intent == "register_transaction" and intent.draft is not None:
        await _handle_transaction_candidate(update, context, text)
    elif intent.intent == "show_history":
        await _show_history(update, context, as_edit=False)
    elif intent.intent == "show_summary":
        await _show_summary(update, context, as_edit=False)
    elif intent.intent == "update_salary":
        amount = intent.entities.get("amount")
        if amount:
            with runtime.db.session() as session:
                runtime.users.update_salary(session, str(update.effective_user.id), Decimal(amount))
            await update.message.reply_text("Salario atualizado.", reply_markup=_menu_markup())
        else:
            context.user_data["state"] = STATE_AWAITING_SALARY_UPDATE
            await update.message.reply_text("Me diga o novo salario mensal.")
    elif intent.intent == "request_report":
        await _send_report(update, context, as_edit=False)
    else:
        await update.message.reply_text(
            "Posso registrar transacoes, mostrar historico, resumir seu mes ou gerar relatorio. Ex.: 'gastei 32 no uber'.",
            reply_markup=_menu_markup(),
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Erro ao processar update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Ocorreu um erro interno. Tente novamente.")


def build_application() -> Application:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    runtime = BotRuntime(settings)
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["runtime"] = runtime
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registro", command_registro))
    app.add_handler(CommandHandler("historico", command_historico))
    app.add_handler(CommandHandler("salario", command_summary))
    app.add_handler(CommandHandler("dinheiro", command_summary))
    app.add_handler(CommandHandler("relatorio", command_report))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_error_handler(error_handler)
    return app


def main() -> None:
    application = build_application()
    logger.info("Iniciando ChamaLeon em polling")
    application.run_polling()
