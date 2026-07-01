from __future__ import annotations

import csv
import io
import json
from datetime import (
    UTC,
    date,
    datetime,
)
from decimal import Decimal
from typing import Any
from uuid import (
    UUID,
    uuid4,
)

from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import (
    delete,
    func,
    select,
)
from sqlalchemy.orm import Session

from app.admin_models import (
    AdminAuditLog,
)
from app.closing_models import (
    MonthlyClosingState,
)
from app.core.security import (
    verify_password,
)
from app.data_models import (
    DataOperationLog,
)
from app.data_schemas import (
    ClearFinancialDataInput,
    DataExportFile,
    DataImportCounts,
    DataImportFormat,
    DataImportMode,
    DataImportPreviewRead,
    DataImportRequest,
    DataImportResultRead,
    DataMessageRead,
    DataOperationLogRead,
    DataSummaryRead,
    DeleteAccountInput,
)
from app.lume_models import (
    LumeConversation,
    LumeMessage,
)
from app.models.entities import (
    Account,
    Category,
    MonthlyClosing,
    Transaction,
    TransactionGroup,
    User,
    UserSession,
)
from app.models.enums import (
    AccountType,
    CategoryApplication,
    GroupType,
    TransactionOrigin,
    TransactionStatus,
    TransactionType,
    UserRole,
    UserStatus,
)
from app.notification_models import (
    Notification,
    NotificationPreference,
)
from app.onboarding_models import (
    UserOnboardingState,
)
from app.planning_models import (
    PlanningScenario,
)
from app.services import create_defaults
from app.user_preferences_models import (
    UserPreference,
)


BACKUP_VERSION = 1
BACKUP_FORMAT = "prumo_backup"
MAX_PREVIEW_SAMPLE = 10


def _now() -> datetime:
    return datetime.now(UTC)


def _decimal(
    value: Any,
    default: str = "0",
) -> Decimal:
    if value in {
        None,
        "",
    }:
        return Decimal(default)

    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(
            f"Valor monetário inválido: {value}"
        ) from exc


def _date(
    value: Any,
) -> date:
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(
            str(value)[:10]
        )
    except Exception as exc:
        raise ValueError(
            f"Data inválida: {value}"
        ) from exc


def _datetime(
    value: Any,
) -> datetime | None:
    if value in {
        None,
        "",
    }:
        return None

    if isinstance(value, datetime):
        return value

    try:
        parsed = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=UTC
            )

        return parsed
    except Exception as exc:
        raise ValueError(
            f"Data e hora inválida: {value}"
        ) from exc


def _normalize(
    value: Any,
) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .split()
    )


def _enum_value(
    enum_class,
    value: Any,
    label: str,
):
    try:
        return enum_class(
            str(value)
        )
    except Exception as exc:
        raise ValueError(
            f"{label} inválido: {value}"
        ) from exc


def _log(
    db: Session,
    *,
    user_id: UUID,
    action: str,
    data_format: str,
    status_value: str,
    summary: dict,
) -> None:
    db.add(
        DataOperationLog(
            user_id=user_id,
            action=action,
            data_format=data_format,
            status=status_value,
            summary=summary,
        )
    )


def _account_dict(
    account: Account,
) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "name": account.name,
        "type": account.type.value,
        "is_default": (
            account.is_default
        ),
        "is_active": (
            account.is_active
        ),
        "closing_day": (
            account.closing_day
        ),
        "due_day": account.due_day,
        "created_at": (
            account.created_at
            .isoformat()
        ),
        "updated_at": (
            account.updated_at
            .isoformat()
        ),
    }


def _category_dict(
    category: Category,
) -> dict[str, Any]:
    return {
        "id": str(category.id),
        "name": category.name,
        "application": (
            category.application.value
        ),
        "is_active": (
            category.is_active
        ),
        "is_system_default": (
            category.is_system_default
        ),
        "created_at": (
            category.created_at
            .isoformat()
        ),
        "updated_at": (
            category.updated_at
            .isoformat()
        ),
    }


def _group_dict(
    group: TransactionGroup,
) -> dict[str, Any]:
    return {
        "id": str(group.id),
        "account_id": (
            str(group.account_id)
        ),
        "category_id": (
            str(group.category_id)
            if group.category_id
            else None
        ),
        "group_type": (
            group.group_type.value
        ),
        "transaction_type": (
            group
            .transaction_type
            .value
        ),
        "origin": group.origin.value,
        "description": (
            group.description
        ),
        "notes": group.notes,
        "base_amount": (
            str(group.base_amount)
        ),
        "total_amount": (
            str(group.total_amount)
            if group.total_amount
            is not None
            else None
        ),
        "occurrence_count": (
            group.occurrence_count
        ),
        "generated_occurrences": (
            group
            .generated_occurrences
        ),
        "start_date": (
            group.start_date
            .isoformat()
        ),
        "end_date": (
            group.end_date
            .isoformat()
            if group.end_date
            else None
        ),
        "generated_until": (
            group.generated_until
            .isoformat()
            if group.generated_until
            else None
        ),
        "is_indefinite": (
            group.is_indefinite
        ),
        "is_active": (
            group.is_active
        ),
        "created_at": (
            group.created_at
            .isoformat()
        ),
        "updated_at": (
            group.updated_at
            .isoformat()
        ),
    }


def _transaction_dict(
    transaction: Transaction,
) -> dict[str, Any]:
    return {
        "id": str(transaction.id),
        "group_id": (
            str(transaction.group_id)
        ),
        "account_id": (
            str(transaction.account_id)
        ),
        "category_id": (
            str(transaction.category_id)
            if transaction.category_id
            else None
        ),
        "transaction_type": (
            transaction
            .transaction_type
            .value
        ),
        "status": (
            transaction.status.value
        ),
        "description": (
            transaction.description
        ),
        "notes": transaction.notes,
        "amount": (
            str(transaction.amount)
        ),
        "occurrence_date": (
            transaction
            .occurrence_date
            .isoformat()
        ),
        "due_date": (
            transaction.due_date
            .isoformat()
        ),
        "completed_at": (
            transaction.completed_at
            .isoformat()
            if transaction.completed_at
            else None
        ),
        "cancelled_at": (
            transaction.cancelled_at
            .isoformat()
            if transaction.cancelled_at
            else None
        ),
        "sequence_number": (
            transaction
            .sequence_number
        ),
        "created_at": (
            transaction.created_at
            .isoformat()
        ),
        "updated_at": (
            transaction.updated_at
            .isoformat()
        ),
    }


def _closing_dict(
    closing: MonthlyClosing,
) -> dict[str, Any]:
    return {
        "id": str(closing.id),
        "reference_month": (
            closing.reference_month
            .isoformat()
        ),
        "first_closed_at": (
            closing.first_closed_at
            .isoformat()
        ),
        "last_updated_at": (
            closing.last_updated_at
            .isoformat()
        ),
        "update_count": (
            closing.update_count
        ),
        "income_total": (
            str(closing.income_total)
        ),
        "expense_total": (
            str(closing.expense_total)
        ),
        "projected_result": (
            str(
                closing
                .projected_result
            )
        ),
        "pending_count": (
            closing.pending_count
        ),
        "notes": closing.notes,
        "lume_summary": (
            closing.lume_summary
        ),
        "created_at": (
            closing.created_at
            .isoformat()
        ),
        "updated_at": (
            closing.updated_at
            .isoformat()
        ),
    }


def _closing_state_dict(
    state: MonthlyClosingState,
) -> dict[str, Any]:
    return {
        "id": str(state.id),
        "closing_id": (
            str(state.closing_id)
        ),
        "status": state.status,
        "snapshot_version": (
            state.snapshot_version
        ),
        "snapshot": state.snapshot,
        "closed_at": (
            state.closed_at
            .isoformat()
        ),
        "reopened_at": (
            state.reopened_at
            .isoformat()
            if state.reopened_at
            else None
        ),
        "created_at": (
            state.created_at
            .isoformat()
        ),
        "updated_at": (
            state.updated_at
            .isoformat()
        ),
    }



def _planning_scenario_dict(
    scenario: PlanningScenario,
) -> dict[str, Any]:
    return {
        "id": str(scenario.id),
        "description": (
            scenario.description
        ),
        "notes": scenario.notes,
        "transaction_type": (
            scenario
            .transaction_type
            .value
        ),
        "group_type": (
            scenario.group_type.value
        ),
        "amount": str(
            scenario.amount
        ),
        "occurrence_count": (
            scenario.occurrence_count
        ),
        "start_date": (
            scenario.start_date
            .isoformat()
        ),
        "is_active": (
            scenario.is_active
        ),
        "created_at": (
            scenario.created_at
            .isoformat()
        ),
        "updated_at": (
            scenario.updated_at
            .isoformat()
        ),
    }


def _lume_conversation_dict(
    conversation:
        LumeConversation,
) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "last_message_at": (
            conversation
            .last_message_at
            .isoformat()
        ),
        "created_at": (
            conversation.created_at
            .isoformat()
        ),
        "updated_at": (
            conversation.updated_at
            .isoformat()
        ),
    }


def _lume_message_dict(
    message: LumeMessage,
) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "conversation_id": (
            str(
                message
                .conversation_id
            )
        ),
        "role": message.role,
        "content": message.content,
        "action_kind": (
            message.action_kind
        ),
        "action_payload": (
            message.action_payload
        ),
        "action_status": (
            message.action_status
        ),
        "action_result_id": (
            message.action_result_id
        ),
        "model_name": (
            message.model_name
        ),
        "input_tokens": (
            message.input_tokens
        ),
        "output_tokens": (
            message.output_tokens
        ),
        "created_at": (
            message.created_at
            .isoformat()
        ),
        "updated_at": (
            message.updated_at
            .isoformat()
        ),
    }


def _preferences_dict(
    preference:
        UserPreference | None,
) -> dict[str, Any] | None:
    if preference is None:
        return None

    return {
        "theme": preference.theme,
        "density": (
            preference.density
        ),
        "reduce_motion": (
            preference.reduce_motion
        ),
        "default_page": (
            preference.default_page
        ),
    }


def _notification_preferences_dict(
    preference:
        NotificationPreference
        | None,
) -> dict[str, Any] | None:
    if preference is None:
        return None

    return {
        "due_soon_enabled": (
            preference
            .due_soon_enabled
        ),
        "due_today_enabled": (
            preference
            .due_today_enabled
        ),
        "overdue_enabled": (
            preference
            .overdue_enabled
        ),
        "browser_notifications_enabled": (
            preference
            .browser_notifications_enabled
        ),
        "reminder_days_csv": (
            preference
            .reminder_days_csv
        ),
    }


def _onboarding_dict(
    state:
        UserOnboardingState | None,
) -> dict[str, Any] | None:
    if state is None:
        return None

    return {
        "status": state.status,
        "current_step": (
            state.current_step
        ),
        "completed_steps": (
            state.completed_steps
        ),
        "draft": state.draft,
        "auto_completed": (
            state.auto_completed
        ),
        "started_at": (
            state.started_at
            .isoformat()
            if state.started_at
            else None
        ),
        "completed_at": (
            state.completed_at
            .isoformat()
            if state.completed_at
            else None
        ),
        "skipped_at": (
            state.skipped_at
            .isoformat()
            if state.skipped_at
            else None
        ),
    }


def get_data_summary(
    db: Session,
    *,
    user_id: UUID,
) -> DataSummaryRead:
    accounts = int(
        db.scalar(
            select(
                func.count(Account.id)
            ).where(
                Account.user_id
                == user_id
            )
        )
        or 0
    )
    categories = int(
        db.scalar(
            select(
                func.count(Category.id)
            ).where(
                Category.user_id
                == user_id
            )
        )
        or 0
    )
    groups = int(
        db.scalar(
            select(
                func.count(
                    TransactionGroup.id
                )
            ).where(
                TransactionGroup.user_id
                == user_id
            )
        )
        or 0
    )
    transactions = int(
        db.scalar(
            select(
                func.count(
                    Transaction.id
                )
            ).where(
                Transaction.user_id
                == user_id
            )
        )
        or 0
    )
    closings = int(
        db.scalar(
            select(
                func.count(
                    MonthlyClosing.id
                )
            ).where(
                MonthlyClosing.user_id
                == user_id
            )
        )
        or 0
    )
    planning_scenarios = int(
        db.scalar(
            select(
                func.count(
                    PlanningScenario.id
                )
            ).where(
                PlanningScenario.user_id
                == user_id
            )
        )
        or 0
    )
    lume_conversations = int(
        db.scalar(
            select(
                func.count(
                    LumeConversation.id
                )
            ).where(
                LumeConversation.user_id
                == user_id
            )
        )
        or 0
    )

    date_bounds = db.execute(
        select(
            func.min(
                Transaction.due_date
            ),
            func.max(
                Transaction.due_date
            ),
        ).where(
            Transaction.user_id
            == user_id
        )
    ).one()

    return DataSummaryRead(
        accounts=accounts,
        categories=categories,
        groups=groups,
        transactions=transactions,
        closings=closings,
        planning_scenarios=(
            planning_scenarios
        ),
        lume_conversations=(
            lume_conversations
        ),
        first_transaction_date=(
            date_bounds[0]
            .isoformat()
            if date_bounds[0]
            else None
        ),
        last_transaction_date=(
            date_bounds[1]
            .isoformat()
            if date_bounds[1]
            else None
        ),
    )


def build_backup(
    db: Session,
    *,
    user: User,
) -> dict[str, Any]:
    accounts = list(
        db.scalars(
            select(Account)
            .where(
                Account.user_id
                == user.id
            )
            .order_by(
                Account.created_at
                .asc()
            )
        )
    )
    categories = list(
        db.scalars(
            select(Category)
            .where(
                Category.user_id
                == user.id
            )
            .order_by(
                Category.created_at
                .asc()
            )
        )
    )
    groups = list(
        db.scalars(
            select(
                TransactionGroup
            )
            .where(
                TransactionGroup.user_id
                == user.id
            )
            .order_by(
                TransactionGroup
                .created_at
                .asc()
            )
        )
    )
    transactions = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id
                == user.id
            )
            .order_by(
                Transaction.due_date
                .asc(),
                Transaction
                .sequence_number
                .asc(),
            )
        )
    )
    closings = list(
        db.scalars(
            select(
                MonthlyClosing
            )
            .where(
                MonthlyClosing.user_id
                == user.id
            )
            .order_by(
                MonthlyClosing
                .reference_month
                .asc()
            )
        )
    )
    closing_states = list(
        db.scalars(
            select(
                MonthlyClosingState
            )
            .where(
                MonthlyClosingState
                .user_id
                == user.id
            )
            .order_by(
                MonthlyClosingState
                .created_at
                .asc()
            )
        )
    )
    planning_scenarios = list(
        db.scalars(
            select(
                PlanningScenario
            )
            .where(
                PlanningScenario.user_id
                == user.id
            )
            .order_by(
                PlanningScenario
                .created_at
                .asc()
            )
        )
    )
    lume_conversations = list(
        db.scalars(
            select(
                LumeConversation
            )
            .where(
                LumeConversation.user_id
                == user.id
            )
            .order_by(
                LumeConversation
                .created_at
                .asc()
            )
        )
    )
    lume_messages = list(
        db.scalars(
            select(
                LumeMessage
            )
            .where(
                LumeMessage.user_id
                == user.id
            )
            .order_by(
                LumeMessage
                .created_at
                .asc()
            )
        )
    )

    preference = db.scalar(
        select(
            UserPreference
        ).where(
            UserPreference.user_id
            == user.id
        )
    )
    notification_preference = (
        db.scalar(
            select(
                NotificationPreference
            ).where(
                NotificationPreference
                .user_id
                == user.id
            )
        )
    )
    onboarding = db.scalar(
        select(
            UserOnboardingState
        ).where(
            UserOnboardingState
            .user_id
            == user.id
        )
    )

    summary = get_data_summary(
        db,
        user_id=user.id,
    )

    backup = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "exported_at": (
            _now().isoformat()
        ),
        "profile": {
            "name": user.name,
            "email": user.email,
        },
        "summary": (
            summary.model_dump()
        ),
        "accounts": [
            _account_dict(item)
            for item in accounts
        ],
        "categories": [
            _category_dict(item)
            for item in categories
        ],
        "transaction_groups": [
            _group_dict(item)
            for item in groups
        ],
        "transactions": [
            _transaction_dict(item)
            for item in transactions
        ],
        "monthly_closings": [
            _closing_dict(item)
            for item in closings
        ],
        "monthly_closing_states": [
            _closing_state_dict(
                item
            )
            for item
            in closing_states
        ],
        "planning_scenarios": [
            _planning_scenario_dict(
                item
            )
            for item
            in planning_scenarios
        ],
        "lume_conversations": [
            _lume_conversation_dict(
                item
            )
            for item
            in lume_conversations
        ],
        "lume_messages": [
            _lume_message_dict(
                item
            )
            for item
            in lume_messages
        ],
        "preferences": (
            _preferences_dict(
                preference
            )
        ),
        "notification_preferences": (
            _notification_preferences_dict(
                notification_preference
            )
        ),
        "onboarding": (
            _onboarding_dict(
                onboarding
            )
        ),
    }

    _log(
        db,
        user_id=user.id,
        action="export_backup",
        data_format=(
            DataImportFormat
            .PRUMO_BACKUP.value
        ),
        status_value="success",
        summary=(
            summary.model_dump()
        ),
    )
    db.commit()

    return backup


def export_backup_file(
    db: Session,
    *,
    user: User,
) -> DataExportFile:
    backup = build_backup(
        db,
        user=user,
    )

    timestamp = (
        _now()
        .strftime(
            "%Y-%m-%d_%H-%M"
        )
    )

    return DataExportFile(
        filename=(
            f"prumo-backup-{timestamp}.json"
        ),
        mime_type=(
            "application/json"
        ),
        content=json.dumps(
            backup,
            ensure_ascii=False,
            indent=2,
        ),
    )


def export_csv_file(
    db: Session,
    *,
    user: User,
) -> DataExportFile:
    rows = db.execute(
        select(
            Transaction,
            TransactionGroup,
            Account,
            Category,
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
            == user.id
        )
        .order_by(
            Transaction.due_date
            .asc(),
            Transaction.description
            .asc(),
        )
    ).all()

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "group_key",
            "group_type",
            "transaction_type",
            "status",
            "description",
            "notes",
            "amount",
            "occurrence_date",
            "due_date",
            "completed_at",
            "cancelled_at",
            "sequence_number",
            "occurrence_count",
            "is_indefinite",
            "is_group_active",
            "account_name",
            "account_type",
            "category_name",
            "category_application",
            "origin",
        ],
        delimiter=";",
    )
    writer.writeheader()

    for (
        transaction,
        group,
        account,
        category,
    ) in rows:
        writer.writerow({
            "group_key": str(group.id),
            "group_type": (
                group.group_type.value
            ),
            "transaction_type": (
                transaction
                .transaction_type
                .value
            ),
            "status": (
                transaction.status.value
            ),
            "description": (
                transaction.description
            ),
            "notes": (
                transaction.notes
                or ""
            ),
            "amount": (
                str(transaction.amount)
            ),
            "occurrence_date": (
                transaction
                .occurrence_date
                .isoformat()
            ),
            "due_date": (
                transaction.due_date
                .isoformat()
            ),
            "completed_at": (
                transaction.completed_at
                .isoformat()
                if transaction.completed_at
                else ""
            ),
            "cancelled_at": (
                transaction.cancelled_at
                .isoformat()
                if transaction.cancelled_at
                else ""
            ),
            "sequence_number": (
                transaction
                .sequence_number
            ),
            "occurrence_count": (
                group.occurrence_count
                or ""
            ),
            "is_indefinite": (
                str(
                    group.is_indefinite
                ).lower()
            ),
            "is_group_active": (
                str(
                    group.is_active
                ).lower()
            ),
            "account_name": (
                account.name
            ),
            "account_type": (
                account.type.value
            ),
            "category_name": (
                category.name
                if category
                else ""
            ),
            "category_application": (
                category
                .application
                .value
                if category
                else ""
            ),
            "origin": (
                group.origin.value
            ),
        })

    summary = get_data_summary(
        db,
        user_id=user.id,
    )

    _log(
        db,
        user_id=user.id,
        action="export_csv",
        data_format=(
            DataImportFormat.CSV.value
        ),
        status_value="success",
        summary=(
            summary.model_dump()
        ),
    )
    db.commit()

    timestamp = (
        _now()
        .strftime(
            "%Y-%m-%d_%H-%M"
        )
    )

    return DataExportFile(
        filename=(
            f"prumo-movimentacoes-{timestamp}.csv"
        ),
        mime_type=(
            "text/csv;charset=utf-8"
        ),
        content=buffer.getvalue(),
    )


def _parse_backup(
    content: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            content
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "O arquivo JSON está inválido."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "O backup precisa ser "
            "um objeto JSON."
        )

    if (
        payload.get("format")
        != BACKUP_FORMAT
    ):
        raise ValueError(
            "Este arquivo não é um "
            "backup reconhecido do Prumo."
        )

    version = payload.get(
        "version"
    )

    if version != BACKUP_VERSION:
        raise ValueError(
            "Versão de backup "
            f"não suportada: {version}."
        )

    for key in (
        "accounts",
        "categories",
        "transaction_groups",
        "transactions",
    ):
        if not isinstance(
            payload.get(key),
            list,
        ):
            raise ValueError(
                f"Seção ausente ou inválida: {key}."
            )

    return payload


def _detect_csv_delimiter(
    content: str,
) -> str:
    first_line = (
        content.splitlines()[0]
        if content.splitlines()
        else ""
    )

    return (
        ";"
        if first_line.count(";")
        >= first_line.count(",")
        else ","
    )


def _parse_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if value is None:
        return default

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    if normalized in {
        "true",
        "1",
        "yes",
        "sim",
    }:
        return True

    if normalized in {
        "false",
        "0",
        "no",
        "não",
        "nao",
        "",
    }:
        return False

    return default


def _parse_csv(
    content: str,
) -> dict[str, Any]:
    delimiter = (
        _detect_csv_delimiter(
            content
        )
    )

    reader = csv.DictReader(
        io.StringIO(content),
        delimiter=delimiter,
    )

    if not reader.fieldnames:
        raise ValueError(
            "O CSV não possui cabeçalho."
        )

    normalized_fields = {
        _normalize(field)
        for field
        in reader.fieldnames
        if field
    }

    required = {
        "transaction_type",
        "description",
        "amount",
        "due_date",
        "account_name",
    }

    missing = (
        required
        - normalized_fields
    )

    if missing:
        raise ValueError(
            "Colunas obrigatórias ausentes: "
            + ", ".join(
                sorted(missing)
            )
        )

    rows: list[
        dict[str, Any]
    ] = []
    errors: list[str] = []

    for index, raw in enumerate(
        reader,
        start=2,
    ):
        normalized_row = {
            _normalize(key): value
            for key, value
            in raw.items()
            if key is not None
        }

        try:
            transaction_type = (
                _enum_value(
                    TransactionType,
                    normalized_row.get(
                        "transaction_type"
                    ),
                    "Tipo da movimentação",
                )
            )
            group_type = (
                _enum_value(
                    GroupType,
                    normalized_row.get(
                        "group_type"
                    )
                    or GroupType.SINGLE.value,
                    "Formato",
                )
            )
            transaction_status = (
                _enum_value(
                    TransactionStatus,
                    normalized_row.get(
                        "status"
                    )
                    or TransactionStatus
                    .PENDING.value,
                    "Status",
                )
            )

            description = (
                str(
                    normalized_row.get(
                        "description"
                    )
                    or ""
                ).strip()
            )

            if not description:
                raise ValueError(
                    "Descrição vazia."
                )

            amount = _decimal(
                normalized_row.get(
                    "amount"
                )
            )

            if amount <= 0:
                raise ValueError(
                    "O valor precisa ser positivo."
                )

            due_date = _date(
                normalized_row.get(
                    "due_date"
                )
            )
            occurrence_date = _date(
                normalized_row.get(
                    "occurrence_date"
                )
                or due_date
            )

            account_name = str(
                normalized_row.get(
                    "account_name"
                )
                or ""
            ).strip()

            if not account_name:
                raise ValueError(
                    "Conta vazia."
                )

            account_type = (
                _enum_value(
                    AccountType,
                    normalized_row.get(
                        "account_type"
                    )
                    or AccountType
                    .IMMEDIATE_PAYMENT
                    .value,
                    "Tipo da conta",
                )
            )

            category_name = str(
                normalized_row.get(
                    "category_name"
                )
                or ""
            ).strip()

            category_application = (
                _enum_value(
                    CategoryApplication,
                    normalized_row.get(
                        "category_application"
                    )
                    or (
                        CategoryApplication
                        .INCOME.value
                        if transaction_type
                        == TransactionType
                        .INCOME
                        else CategoryApplication
                        .EXPENSE.value
                    ),
                    "Aplicação da categoria",
                )
                if category_name
                else None
            )

            origin = _enum_value(
                TransactionOrigin,
                normalized_row.get(
                    "origin"
                )
                or TransactionOrigin
                .MANUAL.value,
                "Origem",
            )

            group_key = str(
                normalized_row.get(
                    "group_key"
                )
                or f"row-{index}"
            ).strip()

            rows.append({
                "row": index,
                "group_key": group_key,
                "group_type": (
                    group_type.value
                ),
                "transaction_type": (
                    transaction_type.value
                ),
                "status": (
                    transaction_status.value
                ),
                "description": (
                    description
                ),
                "notes": (
                    str(
                        normalized_row.get(
                            "notes"
                        )
                        or ""
                    ).strip()
                    or None
                ),
                "amount": str(amount),
                "occurrence_date": (
                    occurrence_date
                    .isoformat()
                ),
                "due_date": (
                    due_date.isoformat()
                ),
                "completed_at": (
                    normalized_row.get(
                        "completed_at"
                    )
                    or None
                ),
                "cancelled_at": (
                    normalized_row.get(
                        "cancelled_at"
                    )
                    or None
                ),
                "sequence_number": int(
                    normalized_row.get(
                        "sequence_number"
                    )
                    or 1
                ),
                "occurrence_count": (
                    int(
                        normalized_row.get(
                            "occurrence_count"
                        )
                    )
                    if normalized_row.get(
                        "occurrence_count"
                    )
                    else None
                ),
                "is_indefinite": (
                    _parse_bool(
                        normalized_row.get(
                            "is_indefinite"
                        )
                    )
                ),
                "is_group_active": (
                    _parse_bool(
                        normalized_row.get(
                            "is_group_active"
                        ),
                        True,
                    )
                ),
                "account_name": (
                    account_name
                ),
                "account_type": (
                    account_type.value
                ),
                "category_name": (
                    category_name
                    or None
                ),
                "category_application": (
                    category_application
                    .value
                    if category_application
                    else None
                ),
                "origin": origin.value,
            })
        except Exception as exc:
            errors.append(
                f"Linha {index}: {exc}"
            )

    return {
        "rows": rows,
        "errors": errors,
    }


def _group_fingerprint(
    *,
    description: str,
    transaction_type: str,
    group_type: str,
    base_amount: Any,
    start_date: Any,
    account_name: str,
    category_name: str | None,
) -> tuple[str, ...]:
    return (
        _normalize(description),
        str(transaction_type),
        str(group_type),
        str(
            _decimal(
                base_amount
            ).quantize(
                Decimal("0.01")
            )
        ),
        str(start_date)[:10],
        _normalize(account_name),
        _normalize(
            category_name
            or ""
        ),
    )


def _existing_fingerprints(
    db: Session,
    *,
    user_id: UUID,
) -> set[tuple[str, ...]]:
    rows = db.execute(
        select(
            TransactionGroup,
            Account.name,
            Category.name,
        )
        .join(
            Account,
            Account.id
            == TransactionGroup
            .account_id,
        )
        .outerjoin(
            Category,
            Category.id
            == TransactionGroup
            .category_id,
        )
        .where(
            TransactionGroup.user_id
            == user_id
        )
    ).all()

    return {
        _group_fingerprint(
            description=(
                group.description
            ),
            transaction_type=(
                group
                .transaction_type
                .value
            ),
            group_type=(
                group.group_type.value
            ),
            base_amount=(
                group.base_amount
            ),
            start_date=(
                group.start_date
            ),
            account_name=(
                account_name
            ),
            category_name=(
                category_name
            ),
        )
        for (
            group,
            account_name,
            category_name,
        ) in rows
    }


def _backup_preview(
    db: Session,
    *,
    user_id: UUID,
    payload: dict[str, Any],
    mode: DataImportMode,
) -> DataImportPreviewRead:
    warnings: list[str] = []
    errors: list[str] = []

    accounts = payload.get(
        "accounts",
        [],
    )
    categories = payload.get(
        "categories",
        [],
    )
    groups = payload.get(
        "transaction_groups",
        [],
    )
    transactions = payload.get(
        "transactions",
        [],
    )
    closings = payload.get(
        "monthly_closings",
        [],
    )
    planning_scenarios = (
        payload.get(
            "planning_scenarios",
            [],
        )
    )
    lume_conversations = (
        payload.get(
            "lume_conversations",
            [],
        )
    )
    lume_messages = (
        payload.get(
            "lume_messages",
            [],
        )
    )

    account_by_id = {
        str(item.get("id")):
            item
        for item in accounts
    }
    category_by_id = {
        str(item.get("id")):
            item
        for item in categories
    }

    existing_account_names = {
        _normalize(name)
        for name in db.scalars(
            select(Account.name)
            .where(
                Account.user_id
                == user_id
            )
        )
    }
    existing_category_names = {
        _normalize(name)
        for name in db.scalars(
            select(Category.name)
            .where(
                Category.user_id
                == user_id
            )
        )
    }
    existing_fingerprints = (
        _existing_fingerprints(
            db,
            user_id=user_id,
        )
    )
    existing_closing_months = {
        item.isoformat()
        for item in db.scalars(
            select(
                MonthlyClosing
                .reference_month
            ).where(
                MonthlyClosing.user_id
                == user_id
            )
        )
    }

    duplicate_accounts = sum(
        1
        for item in accounts
        if _normalize(
            item.get("name")
        )
        in existing_account_names
    )
    duplicate_categories = sum(
        1
        for item in categories
        if _normalize(
            item.get("name")
        )
        in existing_category_names
    )

    duplicate_groups = 0

    for group in groups:
        account = account_by_id.get(
            str(
                group.get(
                    "account_id"
                )
            )
        )
        category = (
            category_by_id.get(
                str(
                    group.get(
                        "category_id"
                    )
                )
            )
            if group.get(
                "category_id"
            )
            else None
        )

        if account is None:
            errors.append(
                "Um grupo referencia "
                "uma conta ausente no backup."
            )
            continue

        fingerprint = (
            _group_fingerprint(
                description=(
                    group.get(
                        "description",
                        "",
                    )
                ),
                transaction_type=(
                    group.get(
                        "transaction_type",
                        "",
                    )
                ),
                group_type=(
                    group.get(
                        "group_type",
                        "",
                    )
                ),
                base_amount=(
                    group.get(
                        "base_amount",
                        "0",
                    )
                ),
                start_date=(
                    group.get(
                        "start_date",
                        "",
                    )
                ),
                account_name=(
                    account.get(
                        "name",
                        "",
                    )
                ),
                category_name=(
                    category.get(
                        "name"
                    )
                    if category
                    else None
                ),
            )
        )

        if (
            fingerprint
            in existing_fingerprints
        ):
            duplicate_groups += 1

    duplicate_closings = sum(
        1
        for item in closings
        if str(
            item.get(
                "reference_month",
                "",
            )
        )[:10]
        in existing_closing_months
    )

    if (
        mode
        == DataImportMode.MERGE
        and duplicate_accounts
    ):
        warnings.append(
            f"{duplicate_accounts} conta(s) "
            "serão reutilizadas pelo nome."
        )

    if (
        mode
        == DataImportMode.MERGE
        and duplicate_categories
    ):
        warnings.append(
            f"{duplicate_categories} categoria(s) "
            "serão reutilizadas pelo nome."
        )

    if duplicate_groups:
        warnings.append(
            f"{duplicate_groups} grupo(s) "
            "parecem já existir."
        )

    if duplicate_closings:
        warnings.append(
            f"{duplicate_closings} fechamento(s) "
            "já existem para o mesmo mês."
        )

    if (
        mode
        == DataImportMode.REPLACE
    ):
        warnings.append(
            "Todos os dados financeiros "
            "atuais serão removidos antes "
            "da restauração."
        )

    preferences_count = sum(
        1
        for key in (
            "preferences",
            "notification_preferences",
            "onboarding",
        )
        if payload.get(key)
        is not None
    )

    counts = DataImportCounts(
        accounts=len(accounts),
        categories=len(categories),
        groups=len(groups),
        transactions=(
            len(transactions)
        ),
        closings=len(closings),
        planning_scenarios=(
            len(planning_scenarios)
        ),
        lume_conversations=(
            len(lume_conversations)
        ),
        lume_messages=(
            len(lume_messages)
        ),
        preferences=(
            preferences_count
        ),
    )

    duplicates = (
        DataImportCounts(
            accounts=(
                duplicate_accounts
            ),
            categories=(
                duplicate_categories
            ),
            groups=(
                duplicate_groups
            ),
            transactions=0,
            closings=(
                duplicate_closings
            ),
            planning_scenarios=0,
            lume_conversations=0,
            lume_messages=0,
            preferences=0,
        )
    )

    will_create = (
        counts
        if mode
        == DataImportMode.REPLACE
        else DataImportCounts(
            accounts=max(
                0,
                counts.accounts
                - duplicates.accounts,
            ),
            categories=max(
                0,
                counts.categories
                - duplicates.categories,
            ),
            groups=max(
                0,
                counts.groups
                - duplicates.groups,
            ),
            transactions=(
                counts.transactions
            ),
            closings=max(
                0,
                counts.closings
                - duplicates.closings,
            ),
            planning_scenarios=(
                counts
                .planning_scenarios
            ),
            lume_conversations=(
                counts
                .lume_conversations
            ),
            lume_messages=(
                counts
                .lume_messages
            ),
            preferences=(
                counts.preferences
            ),
        )
    )

    sample = [
        {
            "description": item.get(
                "description"
            ),
            "group_type": item.get(
                "group_type"
            ),
            "transaction_type":
                item.get(
                    "transaction_type"
                ),
            "start_date": item.get(
                "start_date"
            ),
            "amount": item.get(
                "base_amount"
            ),
        }
        for item in groups[
            :MAX_PREVIEW_SAMPLE
        ]
    ]

    return DataImportPreviewRead(
        data_format=(
            DataImportFormat
            .PRUMO_BACKUP
        ),
        mode=mode,
        valid=not errors,
        source_version=(
            payload.get("version")
        ),
        counts=counts,
        duplicates=duplicates,
        will_create=will_create,
        warnings=list(
            dict.fromkeys(
                warnings
            )
        ),
        errors=list(
            dict.fromkeys(
                errors
            )
        ),
        sample=sample,
    )


def _csv_preview(
    db: Session,
    *,
    user_id: UUID,
    parsed: dict[str, Any],
    mode: DataImportMode,
) -> DataImportPreviewRead:
    rows = parsed["rows"]
    errors = list(
        parsed["errors"]
    )
    warnings: list[str] = []

    existing_account_names = {
        _normalize(name)
        for name in db.scalars(
            select(Account.name)
            .where(
                Account.user_id
                == user_id
            )
        )
    }
    existing_category_names = {
        _normalize(name)
        for name in db.scalars(
            select(Category.name)
            .where(
                Category.user_id
                == user_id
            )
        )
    }
    existing_fingerprints = (
        _existing_fingerprints(
            db,
            user_id=user_id,
        )
    )

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for row in rows:
        grouped.setdefault(
            row["group_key"],
            [],
        ).append(row)

    source_accounts = {
        _normalize(
            row["account_name"]
        ):
            row["account_name"]
        for row in rows
    }
    source_categories = {
        _normalize(
            row["category_name"]
        ):
            row["category_name"]
        for row in rows
        if row["category_name"]
    }

    duplicate_accounts = sum(
        1
        for name
        in source_accounts
        if name
        in existing_account_names
    )
    duplicate_categories = sum(
        1
        for name
        in source_categories
        if name
        in existing_category_names
    )

    duplicate_groups = 0

    for group_rows in grouped.values():
        first = sorted(
            group_rows,
            key=lambda item:
                item[
                    "sequence_number"
                ],
        )[0]

        fingerprint = (
            _group_fingerprint(
                description=(
                    first[
                        "description"
                    ]
                ),
                transaction_type=(
                    first[
                        "transaction_type"
                    ]
                ),
                group_type=(
                    first[
                        "group_type"
                    ]
                ),
                base_amount=(
                    first["amount"]
                ),
                start_date=(
                    first[
                        "occurrence_date"
                    ]
                ),
                account_name=(
                    first[
                        "account_name"
                    ]
                ),
                category_name=(
                    first[
                        "category_name"
                    ]
                ),
            )
        )

        if (
            fingerprint
            in existing_fingerprints
        ):
            duplicate_groups += 1

    if parsed["errors"]:
        warnings.append(
            "Linhas inválidas não serão importadas."
        )

    if duplicate_groups:
        warnings.append(
            f"{duplicate_groups} grupo(s) "
            "parecem já existir."
        )

    if (
        mode
        == DataImportMode.REPLACE
    ):
        warnings.append(
            "O modo Substituir apagará "
            "os dados atuais antes da importação."
        )

    counts = DataImportCounts(
        accounts=len(
            source_accounts
        ),
        categories=len(
            source_categories
        ),
        groups=len(grouped),
        transactions=len(rows),
        closings=0,
        planning_scenarios=0,
        lume_conversations=0,
        lume_messages=0,
        preferences=0,
    )
    duplicates = DataImportCounts(
        accounts=(
            duplicate_accounts
        ),
        categories=(
            duplicate_categories
        ),
        groups=(
            duplicate_groups
        ),
    )

    will_create = (
        counts
        if mode
        == DataImportMode.REPLACE
        else DataImportCounts(
            accounts=max(
                0,
                counts.accounts
                - duplicate_accounts,
            ),
            categories=max(
                0,
                counts.categories
                - duplicate_categories,
            ),
            groups=max(
                0,
                counts.groups
                - duplicate_groups,
            ),
            transactions=(
                counts.transactions
            ),
        )
    )

    return DataImportPreviewRead(
        data_format=(
            DataImportFormat.CSV
        ),
        mode=mode,
        valid=(
            bool(rows)
            and not errors
        ),
        source_version=None,
        counts=counts,
        duplicates=duplicates,
        will_create=will_create,
        warnings=warnings,
        errors=errors,
        sample=[
            {
                "description": (
                    item[
                        "description"
                    ]
                ),
                "transaction_type": (
                    item[
                        "transaction_type"
                    ]
                ),
                "due_date": (
                    item["due_date"]
                ),
                "amount": (
                    item["amount"]
                ),
                "account_name": (
                    item[
                        "account_name"
                    ]
                ),
            }
            for item in rows[
                :MAX_PREVIEW_SAMPLE
            ]
        ],
    )


def preview_import(
    db: Session,
    *,
    user_id: UUID,
    request: DataImportRequest,
) -> DataImportPreviewRead:
    try:
        if (
            request.data_format
            == DataImportFormat
            .PRUMO_BACKUP
        ):
            payload = _parse_backup(
                request.content
            )

            return _backup_preview(
                db,
                user_id=user_id,
                payload=payload,
                mode=request.mode,
            )

        parsed = _parse_csv(
            request.content
        )

        return _csv_preview(
            db,
            user_id=user_id,
            parsed=parsed,
            mode=request.mode,
        )
    except ValueError as exc:
        return DataImportPreviewRead(
            data_format=(
                request.data_format
            ),
            mode=request.mode,
            valid=False,
            source_version=None,
            counts=(
                DataImportCounts()
            ),
            duplicates=(
                DataImportCounts()
            ),
            will_create=(
                DataImportCounts()
            ),
            warnings=[],
            errors=[str(exc)],
            sample=[],
        )


def _clear_user_financial_data(
    db: Session,
    *,
    user_id: UUID,
    include_preferences: bool,
) -> None:
    db.execute(
        delete(Notification)
        .where(
            Notification.user_id
            == user_id
        )
    )
    db.execute(
        delete(LumeMessage)
        .where(
            LumeMessage.user_id
            == user_id
        )
    )
    db.execute(
        delete(LumeConversation)
        .where(
            LumeConversation.user_id
            == user_id
        )
    )
    db.execute(
        delete(PlanningScenario)
        .where(
            PlanningScenario.user_id
            == user_id
        )
    )
    db.execute(
        delete(
            MonthlyClosingState
        ).where(
            MonthlyClosingState
            .user_id
            == user_id
        )
    )
    db.execute(
        delete(MonthlyClosing)
        .where(
            MonthlyClosing.user_id
            == user_id
        )
    )
    db.execute(
        delete(Transaction)
        .where(
            Transaction.user_id
            == user_id
        )
    )
    db.execute(
        delete(
            TransactionGroup
        ).where(
            TransactionGroup.user_id
            == user_id
        )
    )
    db.execute(
        delete(Account)
        .where(
            Account.user_id
            == user_id
        )
    )
    db.execute(
        delete(Category)
        .where(
            Category.user_id
            == user_id
        )
    )

    if include_preferences:
        db.execute(
            delete(UserPreference)
            .where(
                UserPreference.user_id
                == user_id
            )
        )
        db.execute(
            delete(
                NotificationPreference
            ).where(
                NotificationPreference
                .user_id
                == user_id
            )
        )
        db.execute(
            delete(
                UserOnboardingState
            ).where(
                UserOnboardingState
                .user_id
                == user_id
            )
        )


def _rewrite_ids(
    value: Any,
    mapping: dict[
        str,
        str,
    ],
) -> Any:
    if isinstance(value, dict):
        return {
            key: _rewrite_ids(
                item,
                mapping,
            )
            for key, item
            in value.items()
        }

    if isinstance(value, list):
        return [
            _rewrite_ids(
                item,
                mapping,
            )
            for item in value
        ]

    if (
        isinstance(value, str)
        and value in mapping
    ):
        return mapping[value]

    return value


def _restore_preferences(
    db: Session,
    *,
    user_id: UUID,
    payload: dict[str, Any],
) -> int:
    restored = 0

    preference_data = (
        payload.get(
            "preferences"
        )
    )

    if preference_data:
        preference = db.scalar(
            select(
                UserPreference
            ).where(
                UserPreference.user_id
                == user_id
            )
        )

        if preference is None:
            preference = (
                UserPreference(
                    user_id=user_id
                )
            )
            db.add(preference)

        preference.theme = (
            preference_data.get(
                "theme",
                "system",
            )
        )
        preference.density = (
            preference_data.get(
                "density",
                "comfortable",
            )
        )
        preference.reduce_motion = bool(
            preference_data.get(
                "reduce_motion",
                False,
            )
        )
        preference.default_page = (
            preference_data.get(
                "default_page",
                "/home",
            )
        )
        restored += 1

    notification_data = (
        payload.get(
            "notification_preferences"
        )
    )

    if notification_data:
        notification_preference = (
            db.scalar(
                select(
                    NotificationPreference
                ).where(
                    NotificationPreference
                    .user_id
                    == user_id
                )
            )
        )

        if (
            notification_preference
            is None
        ):
            notification_preference = (
                NotificationPreference(
                    user_id=user_id
                )
            )
            db.add(
                notification_preference
            )

        notification_preference.due_soon_enabled = bool(
            notification_data.get(
                "due_soon_enabled",
                True,
            )
        )
        notification_preference.due_today_enabled = bool(
            notification_data.get(
                "due_today_enabled",
                True,
            )
        )
        notification_preference.overdue_enabled = bool(
            notification_data.get(
                "overdue_enabled",
                True,
            )
        )
        notification_preference.browser_notifications_enabled = bool(
            notification_data.get(
                "browser_notifications_enabled",
                False,
            )
        )
        notification_preference.reminder_days_csv = str(
            notification_data.get(
                "reminder_days_csv",
                "1,3,7",
            )
        )
        restored += 1

    onboarding_data = payload.get(
        "onboarding"
    )

    if onboarding_data:
        onboarding = db.scalar(
            select(
                UserOnboardingState
            ).where(
                UserOnboardingState
                .user_id
                == user_id
            )
        )

        if onboarding is None:
            onboarding = (
                UserOnboardingState(
                    user_id=user_id
                )
            )
            db.add(onboarding)

        onboarding.status = str(
            onboarding_data.get(
                "status",
                "completed",
            )
        )
        onboarding.current_step = int(
            onboarding_data.get(
                "current_step",
                6,
            )
        )
        onboarding.completed_steps = (
            onboarding_data.get(
                "completed_steps",
                [],
            )
        )
        onboarding.draft = (
            onboarding_data.get(
                "draft",
                {},
            )
        )
        onboarding.auto_completed = bool(
            onboarding_data.get(
                "auto_completed",
                False,
            )
        )
        onboarding.started_at = (
            _datetime(
                onboarding_data.get(
                    "started_at"
                )
            )
        )
        onboarding.completed_at = (
            _datetime(
                onboarding_data.get(
                    "completed_at"
                )
            )
        )
        onboarding.skipped_at = (
            _datetime(
                onboarding_data.get(
                    "skipped_at"
                )
            )
        )
        restored += 1

    return restored


def _apply_backup(
    db: Session,
    *,
    user: User,
    request: DataImportRequest,
    payload: dict[str, Any],
) -> DataImportResultRead:
    preview = _backup_preview(
        db,
        user_id=user.id,
        payload=payload,
        mode=request.mode,
    )

    if not preview.valid:
        raise HTTPException(
            status_code=(
                status
                .HTTP_400_BAD_REQUEST
            ),
            detail=" ".join(
                preview.errors
            ),
        )

    if (
        request.mode
        == DataImportMode.REPLACE
    ):
        if not verify_password(
            request.current_password
            or "",
            user.password_hash,
        ):
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_401_UNAUTHORIZED
                ),
                detail=(
                    "Senha atual inválida."
                ),
            )

        _clear_user_financial_data(
            db,
            user_id=user.id,
            include_preferences=True,
        )
        db.flush()

    existing_accounts = {
        _normalize(
            account.name
        ): account
        for account in db.scalars(
            select(Account)
            .where(
                Account.user_id
                == user.id
            )
        )
    }
    existing_categories = {
        _normalize(
            category.name
        ): category
        for category in db.scalars(
            select(Category)
            .where(
                Category.user_id
                == user.id
            )
        )
    }
    existing_fingerprints = (
        _existing_fingerprints(
            db,
            user_id=user.id,
        )
    )
    existing_closings = {
        closing
        .reference_month
        .isoformat():
            closing
        for closing in db.scalars(
            select(
                MonthlyClosing
            ).where(
                MonthlyClosing.user_id
                == user.id
            )
        )
    }

    account_map: dict[
        str,
        UUID,
    ] = {}
    category_map: dict[
        str,
        UUID,
    ] = {}
    group_map: dict[
        str,
        UUID,
    ] = {}
    closing_map: dict[
        str,
        UUID,
    ] = {}
    all_id_map: dict[
        str,
        str,
    ] = {}

    created = DataImportCounts()
    skipped = DataImportCounts()
    warnings = list(
        preview.warnings
    )

    imported_accounts = (
        payload.get(
            "accounts",
            [],
        )
    )
    imported_categories = (
        payload.get(
            "categories",
            [],
        )
    )

    for item in imported_accounts:
        old_id = str(
            item.get("id")
        )
        name = str(
            item.get("name")
            or "Conta importada"
        ).strip()
        normalized = _normalize(
            name
        )
        existing = (
            existing_accounts.get(
                normalized
            )
        )

        if existing:
            account_map[
                old_id
            ] = existing.id
            all_id_map[
                old_id
            ] = str(existing.id)
            skipped.accounts += 1
            continue

        account = Account(
            id=uuid4(),
            user_id=user.id,
            name=name,
            type=_enum_value(
                AccountType,
                item.get(
                    "type",
                    AccountType
                    .IMMEDIATE_PAYMENT
                    .value,
                ),
                "Tipo da conta",
            ),
            is_default=False,
            is_active=bool(
                item.get(
                    "is_active",
                    True,
                )
            ),
            closing_day=(
                item.get(
                    "closing_day"
                )
            ),
            due_day=(
                item.get(
                    "due_day"
                )
            ),
        )
        db.add(account)
        db.flush()

        existing_accounts[
            normalized
        ] = account
        account_map[
            old_id
        ] = account.id
        all_id_map[
            old_id
        ] = str(account.id)
        created.accounts += 1

    default_candidates = [
        item
        for item
        in imported_accounts
        if item.get(
            "is_default"
        )
    ]

    if default_candidates:
        default_id = account_map.get(
            str(
                default_candidates[
                    0
                ].get("id")
            )
        )

        if default_id:
            for account in (
                existing_accounts
                .values()
            ):
                account.is_default = (
                    account.id
                    == default_id
                )
    elif existing_accounts:
        if not any(
            account.is_default
            for account in (
                existing_accounts
                .values()
            )
        ):
            next(
                iter(
                    existing_accounts
                    .values()
                )
            ).is_default = True

    for item in imported_categories:
        old_id = str(
            item.get("id")
        )
        name = str(
            item.get("name")
            or "Categoria importada"
        ).strip()
        normalized = _normalize(
            name
        )
        existing = (
            existing_categories.get(
                normalized
            )
        )

        if existing:
            category_map[
                old_id
            ] = existing.id
            all_id_map[
                old_id
            ] = str(existing.id)
            skipped.categories += 1
            continue

        category = Category(
            id=uuid4(),
            user_id=user.id,
            name=name,
            application=_enum_value(
                CategoryApplication,
                item.get(
                    "application",
                    CategoryApplication
                    .BOTH.value,
                ),
                "Aplicação da categoria",
            ),
            is_active=bool(
                item.get(
                    "is_active",
                    True,
                )
            ),
            is_system_default=bool(
                item.get(
                    "is_system_default",
                    False,
                )
            ),
        )
        db.add(category)
        db.flush()

        existing_categories[
            normalized
        ] = category
        category_map[
            old_id
        ] = category.id
        all_id_map[
            old_id
        ] = str(category.id)
        created.categories += 1

    account_by_old_id = {
        str(item.get("id")):
            item
        for item
        in imported_accounts
    }
    category_by_old_id = {
        str(item.get("id")):
            item
        for item
        in imported_categories
    }

    skipped_group_ids: set[
        str
    ] = set()

    for item in payload.get(
        "transaction_groups",
        [],
    ):
        old_id = str(
            item.get("id")
        )
        old_account_id = str(
            item.get(
                "account_id"
            )
        )
        old_category_id = (
            str(
                item.get(
                    "category_id"
                )
            )
            if item.get(
                "category_id"
            )
            else None
        )

        account_item = (
            account_by_old_id.get(
                old_account_id
            )
        )
        category_item = (
            category_by_old_id.get(
                old_category_id
            )
            if old_category_id
            else None
        )

        fingerprint = (
            _group_fingerprint(
                description=(
                    item.get(
                        "description",
                        "",
                    )
                ),
                transaction_type=(
                    item.get(
                        "transaction_type",
                        "",
                    )
                ),
                group_type=(
                    item.get(
                        "group_type",
                        "",
                    )
                ),
                base_amount=(
                    item.get(
                        "base_amount",
                        "0",
                    )
                ),
                start_date=(
                    item.get(
                        "start_date",
                        "",
                    )
                ),
                account_name=(
                    account_item.get(
                        "name",
                        "",
                    )
                    if account_item
                    else ""
                ),
                category_name=(
                    category_item.get(
                        "name"
                    )
                    if category_item
                    else None
                ),
            )
        )

        if (
            request.skip_duplicates
            and fingerprint
            in existing_fingerprints
        ):
            skipped.groups += 1
            skipped_group_ids.add(
                old_id
            )
            continue

        new_account_id = (
            account_map.get(
                old_account_id
            )
        )

        if new_account_id is None:
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_400_BAD_REQUEST
                ),
                detail=(
                    "Um grupo não possui "
                    "uma conta importável."
                ),
            )

        new_category_id = (
            category_map.get(
                old_category_id
            )
            if old_category_id
            else None
        )

        group = TransactionGroup(
            id=uuid4(),
            user_id=user.id,
            account_id=(
                new_account_id
            ),
            category_id=(
                new_category_id
            ),
            group_type=_enum_value(
                GroupType,
                item.get(
                    "group_type"
                ),
                "Formato",
            ),
            transaction_type=(
                _enum_value(
                    TransactionType,
                    item.get(
                        "transaction_type"
                    ),
                    "Tipo da movimentação",
                )
            ),
            origin=_enum_value(
                TransactionOrigin,
                item.get(
                    "origin",
                    TransactionOrigin
                    .MANUAL.value,
                ),
                "Origem",
            ),
            description=str(
                item.get(
                    "description"
                )
                or "Importado"
            ),
            notes=item.get(
                "notes"
            ),
            base_amount=_decimal(
                item.get(
                    "base_amount"
                )
            ),
            total_amount=(
                _decimal(
                    item.get(
                        "total_amount"
                    )
                )
                if item.get(
                    "total_amount"
                )
                not in {
                    None,
                    "",
                }
                else None
            ),
            occurrence_count=(
                item.get(
                    "occurrence_count"
                )
            ),
            generated_occurrences=int(
                item.get(
                    "generated_occurrences",
                    0,
                )
            ),
            start_date=_date(
                item.get(
                    "start_date"
                )
            ),
            end_date=(
                _date(
                    item.get(
                        "end_date"
                    )
                )
                if item.get(
                    "end_date"
                )
                else None
            ),
            generated_until=(
                _date(
                    item.get(
                        "generated_until"
                    )
                )
                if item.get(
                    "generated_until"
                )
                else None
            ),
            is_indefinite=bool(
                item.get(
                    "is_indefinite",
                    False,
                )
            ),
            is_active=bool(
                item.get(
                    "is_active",
                    True,
                )
            ),
        )
        db.add(group)
        db.flush()

        group_map[
            old_id
        ] = group.id
        all_id_map[
            old_id
        ] = str(group.id)
        existing_fingerprints.add(
            fingerprint
        )
        created.groups += 1

    for item in payload.get(
        "transactions",
        [],
    ):
        old_group_id = str(
            item.get(
                "group_id"
            )
        )

        if (
            old_group_id
            in skipped_group_ids
        ):
            skipped.transactions += 1
            continue

        new_group_id = group_map.get(
            old_group_id
        )

        if new_group_id is None:
            skipped.transactions += 1
            continue

        old_account_id = str(
            item.get(
                "account_id"
            )
        )
        old_category_id = (
            str(
                item.get(
                    "category_id"
                )
            )
            if item.get(
                "category_id"
            )
            else None
        )

        transaction = Transaction(
            id=uuid4(),
            group_id=new_group_id,
            user_id=user.id,
            account_id=(
                account_map[
                    old_account_id
                ]
            ),
            category_id=(
                category_map.get(
                    old_category_id
                )
                if old_category_id
                else None
            ),
            transaction_type=(
                _enum_value(
                    TransactionType,
                    item.get(
                        "transaction_type"
                    ),
                    "Tipo da movimentação",
                )
            ),
            status=_enum_value(
                TransactionStatus,
                item.get(
                    "status"
                ),
                "Status",
            ),
            description=str(
                item.get(
                    "description"
                )
                or "Importado"
            ),
            notes=item.get(
                "notes"
            ),
            amount=_decimal(
                item.get(
                    "amount"
                )
            ),
            occurrence_date=_date(
                item.get(
                    "occurrence_date"
                )
            ),
            due_date=_date(
                item.get(
                    "due_date"
                )
            ),
            completed_at=_datetime(
                item.get(
                    "completed_at"
                )
            ),
            cancelled_at=_datetime(
                item.get(
                    "cancelled_at"
                )
            ),
            sequence_number=int(
                item.get(
                    "sequence_number",
                    1,
                )
            ),
        )
        old_transaction_id = str(
            item.get("id")
        )

        db.add(transaction)
        db.flush()

        all_id_map[
            old_transaction_id
        ] = str(
            transaction.id
        )
        created.transactions += 1

    skipped_closing_ids: set[
        str
    ] = set()

    for item in payload.get(
        "monthly_closings",
        [],
    ):
        old_id = str(
            item.get("id")
        )
        reference_month = (
            _date(
                item.get(
                    "reference_month"
                )
            ).replace(day=1)
        )
        key = (
            reference_month
            .isoformat()
        )

        if (
            request.mode
            == DataImportMode.MERGE
            and key
            in existing_closings
        ):
            skipped.closings += 1
            skipped_closing_ids.add(
                old_id
            )
            closing_map[
                old_id
            ] = (
                existing_closings[
                    key
                ].id
            )
            all_id_map[
                old_id
            ] = str(
                existing_closings[
                    key
                ].id
            )
            continue

        closing = MonthlyClosing(
            id=uuid4(),
            user_id=user.id,
            reference_month=(
                reference_month
            ),
            first_closed_at=(
                _datetime(
                    item.get(
                        "first_closed_at"
                    )
                )
                or _now()
            ),
            last_updated_at=(
                _datetime(
                    item.get(
                        "last_updated_at"
                    )
                )
                or _now()
            ),
            update_count=int(
                item.get(
                    "update_count",
                    0,
                )
            ),
            income_total=_decimal(
                item.get(
                    "income_total"
                )
            ),
            expense_total=_decimal(
                item.get(
                    "expense_total"
                )
            ),
            projected_result=_decimal(
                item.get(
                    "projected_result"
                )
            ),
            pending_count=int(
                item.get(
                    "pending_count",
                    0,
                )
            ),
            notes=item.get(
                "notes"
            ),
            lume_summary=item.get(
                "lume_summary"
            ),
        )
        db.add(closing)
        db.flush()

        closing_map[
            old_id
        ] = closing.id
        all_id_map[
            old_id
        ] = str(closing.id)
        existing_closings[
            key
        ] = closing
        created.closings += 1

    for item in payload.get(
        "monthly_closing_states",
        [],
    ):
        old_closing_id = str(
            item.get(
                "closing_id"
            )
        )

        if (
            old_closing_id
            in skipped_closing_ids
        ):
            continue

        new_closing_id = (
            closing_map.get(
                old_closing_id
            )
        )

        if new_closing_id is None:
            continue

        existing_state = db.scalar(
            select(
                MonthlyClosingState
            ).where(
                MonthlyClosingState
                .closing_id
                == new_closing_id
            )
        )

        if existing_state:
            continue

        db.add(
            MonthlyClosingState(
                id=uuid4(),
                closing_id=(
                    new_closing_id
                ),
                user_id=user.id,
                status=str(
                    item.get(
                        "status",
                        "closed",
                    )
                ),
                snapshot_version=int(
                    item.get(
                        "snapshot_version",
                        1,
                    )
                ),
                snapshot=(
                    _rewrite_ids(
                        item.get(
                            "snapshot",
                            {},
                        ),
                        all_id_map,
                    )
                ),
                closed_at=(
                    _datetime(
                        item.get(
                            "closed_at"
                        )
                    )
                    or _now()
                ),
                reopened_at=(
                    _datetime(
                        item.get(
                            "reopened_at"
                        )
                    )
                ),
            )
        )

    for item in payload.get(
        "planning_scenarios",
        [],
    ):
        scenario = PlanningScenario(
            id=uuid4(),
            user_id=user.id,
            description=str(
                item.get(
                    "description"
                )
                or "Cenário importado"
            ),
            notes=item.get(
                "notes"
            ),
            transaction_type=(
                _enum_value(
                    TransactionType,
                    item.get(
                        "transaction_type"
                    ),
                    "Tipo do cenário",
                )
            ),
            group_type=_enum_value(
                GroupType,
                item.get(
                    "group_type"
                ),
                "Formato do cenário",
            ),
            amount=_decimal(
                item.get(
                    "amount"
                )
            ),
            occurrence_count=(
                item.get(
                    "occurrence_count"
                )
            ),
            start_date=_date(
                item.get(
                    "start_date"
                )
            ),
            is_active=bool(
                item.get(
                    "is_active",
                    True,
                )
            ),
        )
        old_scenario_id = str(
            item.get("id")
        )

        db.add(scenario)
        db.flush()

        all_id_map[
            old_scenario_id
        ] = str(scenario.id)
        created.planning_scenarios += 1

    conversation_map: dict[
        str,
        UUID,
    ] = {}

    for item in payload.get(
        "lume_conversations",
        [],
    ):
        conversation = LumeConversation(
            id=uuid4(),
            user_id=user.id,
            title=str(
                item.get(
                    "title"
                )
                or "Conversa importada"
            ),
            last_message_at=(
                _datetime(
                    item.get(
                        "last_message_at"
                    )
                )
                or _now()
            ),
        )
        old_conversation_id = str(
            item.get("id")
        )

        db.add(conversation)
        db.flush()

        conversation_map[
            old_conversation_id
        ] = conversation.id
        all_id_map[
            old_conversation_id
        ] = str(conversation.id)
        created.lume_conversations += 1

    for item in payload.get(
        "lume_messages",
        [],
    ):
        old_conversation_id = str(
            item.get(
                "conversation_id"
            )
        )
        new_conversation_id = (
            conversation_map.get(
                old_conversation_id
            )
        )

        if new_conversation_id is None:
            skipped.lume_messages += 1
            continue

        action_result_id = (
            item.get(
                "action_result_id"
            )
        )

        if (
            action_result_id
            is not None
            and str(action_result_id)
            in all_id_map
        ):
            action_result_id = (
                all_id_map[
                    str(action_result_id)
                ]
            )

        message = LumeMessage(
            id=uuid4(),
            conversation_id=(
                new_conversation_id
            ),
            user_id=user.id,
            role=str(
                item.get(
                    "role"
                )
                or "assistant"
            ),
            content=str(
                item.get(
                    "content"
                )
                or ""
            ),
            action_kind=item.get(
                "action_kind"
            ),
            action_payload=(
                _rewrite_ids(
                    item.get(
                        "action_payload"
                    ),
                    all_id_map,
                )
            ),
            action_status=item.get(
                "action_status"
            ),
            action_result_id=(
                action_result_id
            ),
            model_name=item.get(
                "model_name"
            ),
            input_tokens=item.get(
                "input_tokens"
            ),
            output_tokens=item.get(
                "output_tokens"
            ),
        )
        db.add(message)
        created.lume_messages += 1

    created.preferences = (
        _restore_preferences(
            db,
            user_id=user.id,
            payload=payload,
        )
    )

    _log(
        db,
        user_id=user.id,
        action="import_backup",
        data_format=(
            DataImportFormat
            .PRUMO_BACKUP.value
        ),
        status_value="success",
        summary={
            "mode": request.mode.value,
            "created": (
                created.model_dump()
            ),
            "skipped": (
                skipped.model_dump()
            ),
        },
    )

    db.commit()

    return DataImportResultRead(
        message=(
            "Backup restaurado "
            "com sucesso."
        ),
        created=created,
        skipped=skipped,
        warnings=list(
            dict.fromkeys(
                warnings
            )
        ),
    )


def _apply_csv(
    db: Session,
    *,
    user: User,
    request: DataImportRequest,
    parsed: dict[str, Any],
) -> DataImportResultRead:
    preview = _csv_preview(
        db,
        user_id=user.id,
        parsed=parsed,
        mode=request.mode,
    )

    if not preview.valid:
        raise HTTPException(
            status_code=(
                status
                .HTTP_400_BAD_REQUEST
            ),
            detail=" ".join(
                preview.errors
            ),
        )

    if (
        request.mode
        == DataImportMode.REPLACE
    ):
        if not verify_password(
            request.current_password
            or "",
            user.password_hash,
        ):
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_401_UNAUTHORIZED
                ),
                detail=(
                    "Senha atual inválida."
                ),
            )

        _clear_user_financial_data(
            db,
            user_id=user.id,
            include_preferences=False,
        )
        db.flush()

    accounts = {
        _normalize(
            item.name
        ): item
        for item in db.scalars(
            select(Account)
            .where(
                Account.user_id
                == user.id
            )
        )
    }
    categories = {
        _normalize(
            item.name
        ): item
        for item in db.scalars(
            select(Category)
            .where(
                Category.user_id
                == user.id
            )
        )
    }
    fingerprints = (
        _existing_fingerprints(
            db,
            user_id=user.id,
        )
    )

    created = DataImportCounts()
    skipped = DataImportCounts()
    warnings = list(
        preview.warnings
    )

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for row in parsed["rows"]:
        grouped.setdefault(
            row["group_key"],
            [],
        ).append(row)

    for group_rows in grouped.values():
        ordered = sorted(
            group_rows,
            key=lambda item:
                item[
                    "sequence_number"
                ],
        )
        first = ordered[0]

        account_key = _normalize(
            first[
                "account_name"
            ]
        )
        account = accounts.get(
            account_key
        )

        if account is None:
            if not request.create_missing_structure:
                raise HTTPException(
                    status_code=(
                        status
                        .HTTP_409_CONFLICT
                    ),
                    detail=(
                        "A conta "
                        f"{first['account_name']} "
                        "não existe."
                    ),
                )

            account = Account(
                user_id=user.id,
                name=first[
                    "account_name"
                ],
                type=_enum_value(
                    AccountType,
                    first[
                        "account_type"
                    ],
                    "Tipo da conta",
                ),
                is_default=(
                    not accounts
                ),
                is_active=True,
            )
            db.add(account)
            db.flush()
            accounts[
                account_key
            ] = account
            created.accounts += 1
        else:
            skipped.accounts += 1

        category = None

        if first["category_name"]:
            category_key = (
                _normalize(
                    first[
                        "category_name"
                    ]
                )
            )
            category = categories.get(
                category_key
            )

            if category is None:
                if not request.create_missing_structure:
                    raise HTTPException(
                        status_code=(
                            status
                            .HTTP_409_CONFLICT
                        ),
                        detail=(
                            "A categoria "
                            f"{first['category_name']} "
                            "não existe."
                        ),
                    )

                category = Category(
                    user_id=user.id,
                    name=first[
                        "category_name"
                    ],
                    application=(
                        _enum_value(
                            CategoryApplication,
                            first[
                                "category_application"
                            ],
                            "Aplicação da categoria",
                        )
                    ),
                    is_active=True,
                    is_system_default=False,
                )
                db.add(category)
                db.flush()
                categories[
                    category_key
                ] = category
                created.categories += 1
            else:
                skipped.categories += 1

        fingerprint = (
            _group_fingerprint(
                description=(
                    first[
                        "description"
                    ]
                ),
                transaction_type=(
                    first[
                        "transaction_type"
                    ]
                ),
                group_type=(
                    first[
                        "group_type"
                    ]
                ),
                base_amount=(
                    first["amount"]
                ),
                start_date=(
                    first[
                        "occurrence_date"
                    ]
                ),
                account_name=(
                    account.name
                ),
                category_name=(
                    category.name
                    if category
                    else None
                ),
            )
        )

        if (
            request.skip_duplicates
            and fingerprint
            in fingerprints
        ):
            skipped.groups += 1
            skipped.transactions += (
                len(ordered)
            )
            continue

        group_type = _enum_value(
            GroupType,
            first["group_type"],
            "Formato",
        )
        amounts = [
            _decimal(
                item["amount"]
            )
            for item in ordered
        ]

        group = TransactionGroup(
            id=uuid4(),
            user_id=user.id,
            account_id=account.id,
            category_id=(
                category.id
                if category
                else None
            ),
            group_type=group_type,
            transaction_type=(
                _enum_value(
                    TransactionType,
                    first[
                        "transaction_type"
                    ],
                    "Tipo da movimentação",
                )
            ),
            origin=_enum_value(
                TransactionOrigin,
                first["origin"],
                "Origem",
            ),
            description=first[
                "description"
            ],
            notes=first["notes"],
            base_amount=(
                amounts[0]
            ),
            total_amount=(
                sum(
                    amounts,
                    Decimal("0"),
                )
                if group_type
                == GroupType
                .INSTALLMENT
                else None
            ),
            occurrence_count=(
                first[
                    "occurrence_count"
                ]
                or (
                    len(ordered)
                    if group_type
                    != GroupType
                    .RECURRING
                    else None
                )
            ),
            generated_occurrences=(
                len(ordered)
            ),
            start_date=_date(
                first[
                    "occurrence_date"
                ]
            ),
            end_date=None,
            generated_until=max(
                _date(
                    item[
                        "due_date"
                    ]
                )
                for item in ordered
            ),
            is_indefinite=(
                first[
                    "is_indefinite"
                ]
            ),
            is_active=(
                first[
                    "is_group_active"
                ]
            ),
        )
        db.add(group)
        db.flush()
        created.groups += 1

        for item in ordered:
            db.add(
                Transaction(
                    id=uuid4(),
                    group_id=group.id,
                    user_id=user.id,
                    account_id=(
                        account.id
                    ),
                    category_id=(
                        category.id
                        if category
                        else None
                    ),
                    transaction_type=(
                        _enum_value(
                            TransactionType,
                            item[
                                "transaction_type"
                            ],
                            "Tipo da movimentação",
                        )
                    ),
                    status=_enum_value(
                        TransactionStatus,
                        item["status"],
                        "Status",
                    ),
                    description=(
                        item[
                            "description"
                        ]
                    ),
                    notes=item["notes"],
                    amount=_decimal(
                        item["amount"]
                    ),
                    occurrence_date=(
                        _date(
                            item[
                                "occurrence_date"
                            ]
                        )
                    ),
                    due_date=_date(
                        item["due_date"]
                    ),
                    completed_at=(
                        _datetime(
                            item[
                                "completed_at"
                            ]
                        )
                    ),
                    cancelled_at=(
                        _datetime(
                            item[
                                "cancelled_at"
                            ]
                        )
                    ),
                    sequence_number=(
                        item[
                            "sequence_number"
                        ]
                    ),
                )
            )
            created.transactions += 1

        fingerprints.add(
            fingerprint
        )

    _log(
        db,
        user_id=user.id,
        action="import_csv",
        data_format=(
            DataImportFormat.CSV.value
        ),
        status_value="success",
        summary={
            "mode": request.mode.value,
            "created": (
                created.model_dump()
            ),
            "skipped": (
                skipped.model_dump()
            ),
        },
    )

    db.commit()

    return DataImportResultRead(
        message=(
            "Movimentações importadas "
            "com sucesso."
        ),
        created=created,
        skipped=skipped,
        warnings=list(
            dict.fromkeys(
                warnings
            )
        ),
    )


def apply_import(
    db: Session,
    *,
    user: User,
    request: DataImportRequest,
) -> DataImportResultRead:
    try:
        if (
            request.data_format
            == DataImportFormat
            .PRUMO_BACKUP
        ):
            payload = _parse_backup(
                request.content
            )

            return _apply_backup(
                db,
                user=user,
                request=request,
                payload=payload,
            )

        parsed = _parse_csv(
            request.content
        )

        return _apply_csv(
            db,
            user=user,
            request=request,
            parsed=parsed,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()

        _log(
            db,
            user_id=user.id,
            action="import",
            data_format=(
                request
                .data_format.value
            ),
            status_value="failed",
            summary={
                "error": str(exc),
            },
        )
        db.commit()

        raise HTTPException(
            status_code=(
                status
                .HTTP_400_BAD_REQUEST
            ),
            detail=(
                "Não foi possível importar: "
                f"{exc}"
            ),
        ) from exc


def clear_financial_data(
    db: Session,
    *,
    user: User,
    payload:
        ClearFinancialDataInput,
) -> DataMessageRead:
    if not verify_password(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail="Senha atual inválida.",
        )

    summary_before = (
        get_data_summary(
            db,
            user_id=user.id,
        )
    )

    _clear_user_financial_data(
        db,
        user_id=user.id,
        include_preferences=False,
    )
    db.flush()

    create_defaults(
        db,
        user,
    )

    _log(
        db,
        user_id=user.id,
        action=(
            "clear_financial_data"
        ),
        data_format="internal",
        status_value="success",
        summary={
            "before": (
                summary_before
                .model_dump()
            ),
        },
    )
    db.commit()

    return DataMessageRead(
        message=(
            "Dados financeiros apagados. "
            "Uma conta PIX e categorias "
            "padrão foram recriadas."
        )
    )


def delete_user_account(
    db: Session,
    *,
    user: User,
    payload:
        DeleteAccountInput,
) -> DataMessageRead:
    if (
        payload.email.lower()
        != user.email.lower()
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_400_BAD_REQUEST
            ),
            detail=(
                "O e-mail informado "
                "não corresponde à conta."
            ),
        )

    if not verify_password(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail="Senha atual inválida.",
        )

    if (
        user.role
        == UserRole.ADMIN
        and user.status
        == UserStatus.ACTIVE
    ):
        active_admins = int(
            db.scalar(
                select(
                    func.count(User.id)
                ).where(
                    User.role
                    == UserRole.ADMIN,
                    User.status
                    == UserStatus.ACTIVE,
                )
            )
            or 0
        )

        if active_admins <= 1:
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_409_CONFLICT
                ),
                detail=(
                    "Promova outro usuário "
                    "a administrador antes "
                    "de excluir o último "
                    "administrador ativo."
                ),
            )

    db.execute(
        delete(AdminAuditLog)
        .where(
            AdminAuditLog.admin_user_id
            == user.id
        )
    )
    db.execute(
        delete(UserSession)
        .where(
            UserSession.user_id
            == user.id
        )
    )
    db.delete(user)
    db.commit()

    return DataMessageRead(
        message=(
            "Conta excluída "
            "definitivamente."
        )
    )


def list_data_history(
    db: Session,
    *,
    user_id: UUID,
    page: int,
    page_size: int,
) -> list[
    DataOperationLogRead
]:
    rows = list(
        db.scalars(
            select(
                DataOperationLog
            )
            .where(
                DataOperationLog.user_id
                == user_id
            )
            .order_by(
                DataOperationLog
                .created_at
                .desc()
            )
            .offset(
                (page - 1)
                * page_size
            )
            .limit(page_size)
        )
    )

    return [
        DataOperationLogRead
        .model_validate(item)
        for item in rows
    ]
