from __future__ import annotations

import json
from collections import defaultdict
from datetime import (
    UTC,
    date,
    datetime,
    timedelta,
)
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import (
    HTTPException,
    status,
)
from google import genai
from google.genai import types
from pydantic import ValidationError
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.lume_models import (
    LumeConversation,
    LumeMessage,
)
from app.lume_schemas import (
    LumeActionKind,
    LumeActionRead,
    LumeActionResult,
    LumeActionStatus,
    LumeConversationRead,
    LumeMessageRead,
    LumeModelOutput,
    LumeRole,
    LumeSendResponse,
    LumeSummaryRead,
)
from app.models.entities import (
    Account,
    Category,
    Transaction,
    TransactionGroup,
)
from app.models.enums import (
    CategoryApplication,
    GroupType,
    TransactionOrigin,
    TransactionStatus,
    TransactionType,
)
from app.planning_models import PlanningScenario
from app.planning_schemas import (
    PlanningScenarioWrite,
)
from app.schemas import GroupCreate
from app.services import (
    add_months,
    create_group,
)


DAILY_MESSAGE_LIMIT = 40
MAX_CONTEXT_TRANSACTIONS = 300
MAX_HISTORY_MESSAGES = 12


SYSTEM_INSTRUCTION = """
Você é o Lume, assistente financeiro do Prumo.

Regras obrigatórias:
1. Responda sempre em português do Brasil, de forma direta, útil e acolhedora.
2. Use SOMENTE os dados financeiros enviados no contexto. Nunca invente valores.
3. Quando não houver dados suficientes, diga claramente o que está faltando.
4. Não dê garantias de investimento, crédito ou resultado financeiro.
5. Você nunca executa SQL e nunca acessa o banco diretamente.
6. Para criar movimentações ou cenários, apenas proponha uma ação estruturada.
7. Toda ação precisa de confirmação explícita no aplicativo antes de ser executada.
8. Use IDs de conta e categoria exatamente como aparecem no contexto.
9. Se o usuário não indicar conta, use a conta marcada como padrão.
10. Categoria pode ficar vazia quando não houver correspondência segura.
11. Para parcelamento, action_amount é o VALOR TOTAL e occurrence_count é a
    quantidade de parcelas.
12. Para recorrência sem prazo final, use action_is_indefinite=true.
13. Para perguntas analíticas, explique os números usados na conclusão.
14. Não proponha ação quando o usuário estiver apenas fazendo uma pergunta.
15. Quando o usuário disser "simule", "e se", "posso assumir" ou pedir uma
    análise hipotética, proponha create_planning_scenario, nunca uma
    movimentação real.
16. Só proponha create_transaction quando ele pedir claramente para registrar,
    lançar, criar ou adicionar uma movimentação real.
17. Retorne no máximo três sugestões curtas para a próxima pergunta.
""".strip()


def _as_float(
    value: Decimal | int | float,
) -> float:
    return float(value)


def _month_key(
    value: date,
) -> str:
    return value.strftime("%Y-%m")


def _owned_conversation(
    db: Session,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> LumeConversation:
    conversation = db.scalar(
        select(LumeConversation).where(
            LumeConversation.id
            == conversation_id,
            LumeConversation.user_id
            == user_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversa do Lume não encontrada.",
        )

    return conversation


def _serialize_message(
    message: LumeMessage,
    *,
    suggestions: list[str] | None = None,
) -> LumeMessageRead:
    action = None

    if (
        message.action_kind
        and message.action_payload
        and message.action_status
    ):
        action = LumeActionRead(
            message_id=message.id,
            kind=LumeActionKind(
                message.action_kind
            ),
            payload=message.action_payload,
            status=LumeActionStatus(
                message.action_status
            ),
            result_id=(
                message.action_result_id
            ),
        )

    return LumeMessageRead(
        id=message.id,
        conversation_id=(
            message.conversation_id
        ),
        role=LumeRole(message.role),
        content=message.content,
        created_at=message.created_at,
        suggestions=suggestions or [],
        action=action,
    )


def list_conversations(
    db: Session,
    *,
    user_id: UUID,
) -> list[LumeConversationRead]:
    conversations = list(
        db.scalars(
            select(LumeConversation)
            .where(
                LumeConversation.user_id
                == user_id,
            )
            .order_by(
                LumeConversation
                .last_message_at
                .desc(),
            )
        )
    )

    if not conversations:
        return []

    counts = dict(
        db.execute(
            select(
                LumeMessage.conversation_id,
                func.count(
                    LumeMessage.id
                ),
            )
            .where(
                LumeMessage.user_id
                == user_id,
                LumeMessage
                .conversation_id
                .in_(
                    [
                        item.id
                        for item
                        in conversations
                    ]
                ),
            )
            .group_by(
                LumeMessage
                .conversation_id
            )
        ).all()
    )

    return [
        LumeConversationRead(
            id=conversation.id,
            title=conversation.title,
            last_message_at=(
                conversation
                .last_message_at
            ),
            message_count=int(
                counts.get(
                    conversation.id,
                    0,
                )
            ),
        )
        for conversation in conversations
    ]


def list_messages(
    db: Session,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> list[LumeMessageRead]:
    _owned_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    messages = list(
        db.scalars(
            select(LumeMessage)
            .where(
                LumeMessage
                .conversation_id
                == conversation_id,
                LumeMessage.user_id
                == user_id,
            )
            .order_by(
                LumeMessage
                .created_at
                .asc(),
            )
        )
    )

    return [
        _serialize_message(message)
        for message in messages
    ]


def delete_conversation(
    db: Session,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> None:
    conversation = _owned_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    db.delete(conversation)
    db.commit()


def _check_daily_limit(
    db: Session,
    *,
    user_id: UUID,
) -> None:
    now = datetime.now(UTC)
    day_start = datetime(
        now.year,
        now.month,
        now.day,
        tzinfo=UTC,
    )

    used = int(
        db.scalar(
            select(
                func.count(
                    LumeMessage.id
                )
            ).where(
                LumeMessage.user_id
                == user_id,
                LumeMessage.role
                == LumeRole.USER.value,
                LumeMessage.created_at
                >= day_start,
            )
        )
        or 0
    )

    if used >= DAILY_MESSAGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Você atingiu o limite diário "
                "de mensagens do Lume."
            ),
        )


def _build_financial_context(
    db: Session,
    *,
    user_id: UUID,
) -> dict[str, Any]:
    accounts = list(
        db.scalars(
            select(Account)
            .where(
                Account.user_id == user_id,
                Account.is_active.is_(True),
            )
            .order_by(
                Account.is_default.desc(),
                Account.name.asc(),
            )
        )
    )

    categories = list(
        db.scalars(
            select(Category)
            .where(
                Category.user_id
                == user_id,
                Category.is_active.is_(True),
            )
            .order_by(
                Category.name.asc(),
            )
        )
    )

    period_start = add_months(
        date.today().replace(day=1),
        -23,
    )

    rows = db.execute(
        select(
            Transaction,
            TransactionGroup.group_type,
            TransactionGroup.occurrence_count,
            TransactionGroup.generated_occurrences,
            Account.name,
            Category.name,
        )
        .join(
            TransactionGroup,
            TransactionGroup.id
            == Transaction.group_id,
        )
        .join(
            Account,
            Account.id
            == Transaction.account_id,
        )
        .outerjoin(
            Category,
            Category.id
            == Transaction.category_id,
        )
        .where(
            Transaction.user_id
            == user_id,
            Transaction.due_date
            >= period_start,
        )
        .order_by(
            Transaction.due_date.desc(),
            Transaction.created_at.desc(),
        )
        .limit(
            MAX_CONTEXT_TRANSACTIONS
        )
    ).all()

    scenarios = list(
        db.scalars(
            select(PlanningScenario)
            .where(
                PlanningScenario.user_id
                == user_id,
            )
            .order_by(
                PlanningScenario
                .is_active
                .desc(),
                PlanningScenario
                .start_date
                .asc(),
            )
        )
    )

    monthly: dict[
        str,
        dict[str, float | int],
    ] = defaultdict(
        lambda: {
            "income": 0.0,
            "expense": 0.0,
            "pending": 0,
            "completed": 0,
        }
    )

    by_category: dict[
        str,
        dict[str, float],
    ] = defaultdict(
        lambda: {
            "income": 0.0,
            "expense": 0.0,
        }
    )

    by_account: dict[
        str,
        dict[str, float],
    ] = defaultdict(
        lambda: {
            "income": 0.0,
            "expense": 0.0,
        }
    )

    compact_transactions = []

    for (
        transaction,
        group_type,
        occurrence_count,
        generated_occurrences,
        account_name,
        category_name,
    ) in rows:
        month = _month_key(
            transaction.due_date
        )
        amount = _as_float(
            transaction.amount
        )

        if (
            transaction.status
            != TransactionStatus.CANCELLED
        ):
            if (
                transaction.transaction_type
                == TransactionType.INCOME
            ):
                monthly[month][
                    "income"
                ] += amount
                by_category[
                    category_name
                    or "Sem categoria"
                ]["income"] += amount
                by_account[
                    account_name
                ]["income"] += amount
            else:
                monthly[month][
                    "expense"
                ] += amount
                by_category[
                    category_name
                    or "Sem categoria"
                ]["expense"] += amount
                by_account[
                    account_name
                ]["expense"] += amount

        if (
            transaction.status
            == TransactionStatus.PENDING
        ):
            monthly[month][
                "pending"
            ] += 1
        elif (
            transaction.status
            == TransactionStatus.COMPLETED
        ):
            monthly[month][
                "completed"
            ] += 1

        compact_transactions.append(
            {
                "date": (
                    transaction
                    .due_date
                    .isoformat()
                ),
                "description": (
                    transaction
                    .description
                ),
                "type": (
                    transaction
                    .transaction_type
                    .value
                ),
                "group_type": (
                    group_type.value
                ),
                "status": (
                    transaction
                    .status
                    .value
                ),
                "amount": amount,
                "account": account_name,
                "category": (
                    category_name
                    or "Sem categoria"
                ),
                "sequence": (
                    transaction
                    .sequence_number
                ),
                "total_occurrences": (
                    occurrence_count
                    or generated_occurrences
                ),
            }
        )

    return {
        "today": date.today().isoformat(),
        "data_window": {
            "from": period_start.isoformat(),
            "maximum_transactions": (
                MAX_CONTEXT_TRANSACTIONS
            ),
            "returned_transactions": (
                len(compact_transactions)
            ),
        },
        "accounts": [
            {
                "id": str(account.id),
                "name": account.name,
                "type": account.type.value,
                "is_default": (
                    account.is_default
                ),
            }
            for account in accounts
        ],
        "categories": [
            {
                "id": str(category.id),
                "name": category.name,
                "application": (
                    category
                    .application
                    .value
                ),
            }
            for category in categories
        ],
        "monthly_totals": dict(monthly),
        "category_totals": dict(
            by_category
        ),
        "account_totals": dict(
            by_account
        ),
        "transactions": (
            compact_transactions
        ),
        "planning_scenarios": [
            {
                "id": str(scenario.id),
                "description": (
                    scenario.description
                ),
                "transaction_type": (
                    scenario
                    .transaction_type
                    .value
                ),
                "group_type": (
                    scenario
                    .group_type
                    .value
                ),
                "amount": _as_float(
                    scenario.amount
                ),
                "occurrence_count": (
                    scenario
                    .occurrence_count
                ),
                "start_date": (
                    scenario
                    .start_date
                    .isoformat()
                ),
                "is_active": (
                    scenario.is_active
                ),
            }
            for scenario in scenarios
        ],
    }


def _recent_history(
    db: Session,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> list[dict[str, str]]:
    messages = list(
        db.scalars(
            select(LumeMessage)
            .where(
                LumeMessage
                .conversation_id
                == conversation_id,
                LumeMessage.user_id
                == user_id,
            )
            .order_by(
                LumeMessage
                .created_at
                .desc(),
            )
            .limit(
                MAX_HISTORY_MESSAGES
            )
        )
    )

    messages.reverse()

    return [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in messages
    ]


def _parse_model_output(
    response: Any,
) -> LumeModelOutput:
    parsed = getattr(
        response,
        "parsed",
        None,
    )

    if isinstance(
        parsed,
        LumeModelOutput,
    ):
        return parsed

    if isinstance(parsed, dict):
        return LumeModelOutput.model_validate(
            parsed
        )

    text = getattr(
        response,
        "text",
        None,
    )

    if not text:
        raise ValueError(
            "O Gemini não retornou conteúdo."
        )

    return LumeModelOutput.model_validate_json(
        text
    )


def _parse_uuid(
    value: str | None,
) -> UUID | None:
    if not value:
        return None

    try:
        return UUID(value)
    except ValueError:
        return None


def _prepare_action(
    db: Session,
    *,
    user_id: UUID,
    output: LumeModelOutput,
) -> tuple[
    LumeActionKind | None,
    dict[str, Any] | None,
    str | None,
]:
    if not output.action_kind:
        return None, None, None

    try:
        transaction_type = (
            TransactionType(
                output
                .action_transaction_type
            )
        )
        group_type = GroupType(
            output.action_group_type
        )
    except (
        ValueError,
        TypeError,
    ):
        return (
            None,
            None,
            "Não consegui identificar "
            "o tipo completo da ação.",
        )

    description = (
        output.action_description
        or ""
    ).strip()

    if not description:
        return (
            None,
            None,
            "Preciso de uma descrição "
            "para preparar a ação.",
        )

    if (
        output.action_amount is None
        or output.action_amount <= 0
    ):
        return (
            None,
            None,
            "Preciso de um valor maior "
            "que zero.",
        )

    try:
        start_date = date.fromisoformat(
            output.action_start_date
            or ""
        )
    except ValueError:
        return (
            None,
            None,
            "Preciso de uma data válida "
            "para preparar a ação.",
        )

    amount = Decimal(
        str(output.action_amount)
    ).quantize(
        Decimal("0.01")
    )

    occurrence_count = (
        output.action_occurrence_count
    )

    if (
        group_type
        == GroupType.INSTALLMENT
        and (
            occurrence_count is None
            or occurrence_count < 2
        )
    ):
        return (
            None,
            None,
            "Um parcelamento precisa "
            "ter pelo menos duas parcelas.",
        )

    if (
        group_type
        == GroupType.SINGLE
    ):
        occurrence_count = None

    is_indefinite = bool(
        output.action_is_indefinite
    )

    if (
        group_type
        == GroupType.RECURRING
        and occurrence_count is None
    ):
        is_indefinite = True

    if (
        output.action_kind
        == LumeActionKind
        .CREATE_PLANNING_SCENARIO
        .value
    ):
        payload = {
            "description": description,
            "notes": (
                output.action_notes
            ),
            "transaction_type": (
                transaction_type.value
            ),
            "group_type": (
                group_type.value
            ),
            "amount": str(amount),
            "occurrence_count": (
                occurrence_count
            ),
            "start_date": (
                start_date.isoformat()
            ),
            "is_active": True,
        }

        try:
            PlanningScenarioWrite.model_validate(
                payload
            )
        except ValidationError as exc:
            return (
                None,
                None,
                exc.errors()[0]["msg"],
            )

        return (
            LumeActionKind
            .CREATE_PLANNING_SCENARIO,
            payload,
            None,
        )

    account_id = _parse_uuid(
        output.action_account_id
    )

    if account_id is None:
        account = db.scalar(
            select(Account)
            .where(
                Account.user_id
                == user_id,
                Account.is_active
                .is_(True),
            )
            .order_by(
                Account.is_default
                .desc(),
                Account.created_at
                .asc(),
            )
        )
    else:
        account = db.scalar(
            select(Account).where(
                Account.id == account_id,
                Account.user_id
                == user_id,
                Account.is_active
                .is_(True),
            )
        )

    if account is None:
        return (
            None,
            None,
            "Não encontrei uma conta "
            "ativa para esse lançamento.",
        )

    category_id = _parse_uuid(
        output.action_category_id
    )
    category = None

    if category_id is not None:
        category = db.scalar(
            select(Category).where(
                Category.id
                == category_id,
                Category.user_id
                == user_id,
                Category.is_active
                .is_(True),
            )
        )

        if category is None:
            return (
                None,
                None,
                "A categoria sugerida "
                "não está disponível.",
            )

        expected = (
            CategoryApplication.INCOME
            if transaction_type
            == TransactionType.INCOME
            else CategoryApplication.EXPENSE
        )

        if category.application not in {
            expected,
            CategoryApplication.BOTH,
        }:
            return (
                None,
                None,
                "A categoria sugerida "
                "não combina com o tipo "
                "da movimentação.",
            )

    payload = {
        "group_type": (
            group_type.value
        ),
        "transaction_type": (
            transaction_type.value
        ),
        "description": description,
        "notes": output.action_notes,
        "account_id": str(account.id),
        "category_id": (
            str(category.id)
            if category
            else None
        ),
        "amount": str(amount),
        "occurrence_count": (
            occurrence_count
        ),
        "start_date": (
            start_date.isoformat()
        ),
        "end_date": None,
        "is_indefinite": (
            is_indefinite
        ),
        "origin": (
            TransactionOrigin.AI.value
        ),
        "account_name": account.name,
        "category_name": (
            category.name
            if category
            else None
        ),
    }

    group_payload = {
        key: value
        for key, value
        in payload.items()
        if key not in {
            "account_name",
            "category_name",
        }
    }

    try:
        GroupCreate.model_validate(
            group_payload
        )
    except ValidationError as exc:
        return (
            None,
            None,
            exc.errors()[0]["msg"],
        )

    return (
        LumeActionKind
        .CREATE_TRANSACTION,
        payload,
        None,
    )


def send_message(
    db: Session,
    *,
    user_id: UUID,
    message: str,
    conversation_id: UUID | None,
) -> LumeSendResponse:
    _check_daily_limit(
        db,
        user_id=user_id,
    )

    if conversation_id is None:
        conversation = LumeConversation(
            user_id=user_id,
            title=(
                message[:72]
                if len(message) > 72
                else message
            ),
            last_message_at=(
                datetime.now(UTC)
            ),
        )
        db.add(conversation)
        db.flush()
    else:
        conversation = _owned_conversation(
            db,
            conversation_id=(
                conversation_id
            ),
            user_id=user_id,
        )

    user_message = LumeMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role=LumeRole.USER.value,
        content=message,
    )
    db.add(user_message)
    db.flush()

    financial_context = (
        _build_financial_context(
            db,
            user_id=user_id,
        )
    )
    history = _recent_history(
        db,
        conversation_id=conversation.id,
        user_id=user_id,
    )

    prompt_payload = {
        "financial_context": (
            financial_context
        ),
        "recent_conversation": history,
        "current_user_message": message,
    }

    try:
        client = genai.Client(
            api_key=(
                settings
                .gemini_api_key_value
            )
        )

        response = (
            client.models
            .generate_content(
                model=(
                    settings
                    .gemini_model
                ),
                contents=json.dumps(
                    prompt_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                config=(
                    types
                    .GenerateContentConfig(
                        system_instruction=(
                            SYSTEM_INSTRUCTION
                        ),
                        response_mime_type=(
                            "application/json"
                        ),
                        response_schema=(
                            LumeModelOutput
                        ),
                        temperature=0.15,
                        max_output_tokens=1600,
                    )
                ),
            )
        )

        output = _parse_model_output(
            response
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=(
                status
                .HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "O Lume está "
                "temporariamente "
                "indisponível."
            ),
        ) from exc

    (
        action_kind,
        action_payload,
        action_error,
    ) = _prepare_action(
        db,
        user_id=user_id,
        output=output,
    )

    answer = output.answer.strip()

    if action_error:
        answer = (
            f"{answer}\n\n"
            f"{action_error}"
        )

    usage = getattr(
        response,
        "usage_metadata",
        None,
    )

    assistant_message = LumeMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role=LumeRole.ASSISTANT.value,
        content=answer,
        action_kind=(
            action_kind.value
            if action_kind
            else None
        ),
        action_payload=action_payload,
        action_status=(
            LumeActionStatus
            .PENDING
            .value
            if action_kind
            else None
        ),
        model_name=(
            settings.gemini_model
        ),
        input_tokens=getattr(
            usage,
            "prompt_token_count",
            None,
        ),
        output_tokens=getattr(
            usage,
            "candidates_token_count",
            None,
        ),
    )
    db.add(assistant_message)

    conversation.last_message_at = (
        datetime.now(UTC)
    )

    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)

    suggestions = [
        item.strip()
        for item in output.suggestions
        if item.strip()
    ][:3]

    return LumeSendResponse(
        conversation_id=conversation.id,
        user_message=_serialize_message(
            user_message
        ),
        assistant_message=(
            _serialize_message(
                assistant_message,
                suggestions=suggestions,
            )
        ),
    )


def _owned_pending_action(
    db: Session,
    *,
    message_id: UUID,
    user_id: UUID,
) -> LumeMessage:
    message = db.scalar(
        select(LumeMessage).where(
            LumeMessage.id == message_id,
            LumeMessage.user_id
            == user_id,
            LumeMessage.role
            == LumeRole.ASSISTANT.value,
        )
    )

    if (
        message is None
        or not message.action_kind
        or not message.action_payload
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ação do Lume não encontrada.",
        )

    if (
        message.action_status
        != LumeActionStatus
        .PENDING
        .value
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Essa ação já foi "
                "respondida."
            ),
        )

    return message


def confirm_action(
    db: Session,
    *,
    message_id: UUID,
    user_id: UUID,
) -> LumeActionResult:
    message = _owned_pending_action(
        db,
        message_id=message_id,
        user_id=user_id,
    )

    try:
        if (
            message.action_kind
            == LumeActionKind
            .CREATE_TRANSACTION
            .value
        ):
            raw_payload = dict(
                message.action_payload
                or {}
            )
            raw_payload.pop(
                "account_name",
                None,
            )
            raw_payload.pop(
                "category_name",
                None,
            )

            payload = (
                GroupCreate
                .model_validate(
                    raw_payload
                )
            )

            group = create_group(
                db,
                user_id,
                payload,
            )
            result_type = (
                "transaction_group"
            )
            result_id = str(group.id)
            confirmation_text = (
                "Movimentação criada "
                "com sucesso."
            )
        else:
            payload = (
                PlanningScenarioWrite
                .model_validate(
                    message.action_payload
                )
            )
            scenario = PlanningScenario(
                user_id=user_id,
                **payload.model_dump(),
            )
            db.add(scenario)
            db.flush()

            result_type = (
                "planning_scenario"
            )
            result_id = str(
                scenario.id
            )
            confirmation_text = (
                "Cenário adicionado ao "
                "planejamento."
            )

        message.action_status = (
            LumeActionStatus
            .CONFIRMED
            .value
        )
        message.action_result_id = (
            result_id
        )

        follow_up = LumeMessage(
            conversation_id=(
                message.conversation_id
            ),
            user_id=user_id,
            role=(
                LumeRole.ASSISTANT.value
            ),
            content=confirmation_text,
        )
        db.add(follow_up)

        conversation = (
            _owned_conversation(
                db,
                conversation_id=(
                    message
                    .conversation_id
                ),
                user_id=user_id,
            )
        )
        conversation.last_message_at = (
            datetime.now(UTC)
        )

        db.commit()
        db.refresh(follow_up)

        return LumeActionResult(
            success=True,
            message=confirmation_text,
            result_type=result_type,
            result_id=result_id,
            assistant_message=(
                _serialize_message(
                    follow_up
                )
            ),
        )
    except (
        HTTPException,
        ValidationError,
        ValueError,
    ) as exc:
        db.rollback()

        stored_message = db.scalar(
            select(LumeMessage).where(
                LumeMessage.id
                == message_id,
                LumeMessage.user_id
                == user_id,
            )
        )

        if stored_message:
            stored_message.action_status = (
                LumeActionStatus
                .FAILED
                .value
            )
            db.commit()

        detail = (
            exc.detail
            if isinstance(
                exc,
                HTTPException,
            )
            else str(exc)
        )

        raise HTTPException(
            status_code=(
                status
                .HTTP_400_BAD_REQUEST
            ),
            detail=detail,
        ) from exc


def cancel_action(
    db: Session,
    *,
    message_id: UUID,
    user_id: UUID,
) -> LumeActionResult:
    message = _owned_pending_action(
        db,
        message_id=message_id,
        user_id=user_id,
    )
    message.action_status = (
        LumeActionStatus
        .CANCELLED
        .value
    )

    follow_up = LumeMessage(
        conversation_id=(
            message.conversation_id
        ),
        user_id=user_id,
        role=LumeRole.ASSISTANT.value,
        content=(
            "Tudo bem. A ação foi "
            "cancelada e nenhum dado "
            "foi alterado."
        ),
    )
    db.add(follow_up)

    conversation = _owned_conversation(
        db,
        conversation_id=(
            message.conversation_id
        ),
        user_id=user_id,
    )
    conversation.last_message_at = (
        datetime.now(UTC)
    )

    db.commit()
    db.refresh(follow_up)

    return LumeActionResult(
        success=True,
        message=follow_up.content,
        assistant_message=(
            _serialize_message(
                follow_up
            )
        ),
    )


def get_home_summary(
    db: Session,
    *,
    user_id: UUID,
) -> LumeSummaryRead:
    today = date.today()
    month_start = today.replace(day=1)
    month_end = add_months(
        month_start,
        1,
    )
    upcoming_end = today + timedelta(
        days=7
    )

    transactions = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id
                == user_id,
                Transaction.due_date
                >= month_start,
                Transaction.due_date
                < month_end,
                Transaction.status
                != TransactionStatus
                .CANCELLED,
            )
        )
    )

    income = sum(
        (
            transaction.amount
            for transaction
            in transactions
            if (
                transaction
                .transaction_type
                == TransactionType.INCOME
            )
        ),
        Decimal("0"),
    )
    expense = sum(
        (
            transaction.amount
            for transaction
            in transactions
            if (
                transaction
                .transaction_type
                == TransactionType.EXPENSE
            )
        ),
        Decimal("0"),
    )
    pending = [
        transaction
        for transaction in transactions
        if (
            transaction.status
            == TransactionStatus.PENDING
        )
    ]
    overdue = [
        transaction
        for transaction in pending
        if transaction.due_date < today
    ]
    upcoming = sum(
        (
            transaction.amount
            for transaction in pending
            if (
                today
                <= transaction.due_date
                <= upcoming_end
            )
        ),
        Decimal("0"),
    )

    result = income - expense

    if overdue:
        insight = (
            f"Há {len(overdue)} "
            "pendência"
            f"{'s' if len(overdue) != 1 else ''} "
            "atrasada"
            f"{'s' if len(overdue) != 1 else ''}. "
            "Vale priorizar esses "
            "compromissos."
        )
    elif result < 0:
        insight = (
            "As despesas previstas "
            "superam as receitas neste "
            "mês. Revise os maiores "
            "gastos e o planejamento."
        )
    elif expense > 0 and income > 0:
        percentage = (
            float(expense / income)
            * 100
        )
        insight = (
            "As despesas representam "
            f"{percentage:.1f}% das "
            "receitas previstas neste "
            "mês."
        )
    else:
        insight = (
            "Ainda há poucos dados "
            "neste mês. O Lume ficará "
            "mais preciso conforme você "
            "registrar movimentações."
        )

    return LumeSummaryRead(
        reference_month=(
            month_start.isoformat()
        ),
        income=_as_float(income),
        expense=_as_float(expense),
        result=_as_float(result),
        pending_count=len(pending),
        overdue_count=len(overdue),
        upcoming_7_days=_as_float(
            upcoming
        ),
        insight=insight,
        suggestions=[
            "Onde estou gastando mais?",
            "Quanto ainda falta pagar este mês?",
            "Posso assumir uma nova parcela?",
        ],
    )
