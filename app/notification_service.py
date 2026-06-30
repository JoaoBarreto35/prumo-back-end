from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Transaction
from app.models.enums import TransactionStatus
from app.notification_models import (
    Notification,
    NotificationPreference,
)
from app.notification_schemas import (
    NotificationCountRead,
    NotificationListRead,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    NotificationSeverity,
    NotificationSyncRead,
    NotificationType,
)


APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")
GENERATED_TYPES = {
    NotificationType.DUE_SOON.value,
    NotificationType.DUE_TODAY.value,
    NotificationType.OVERDUE.value,
}


def _now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def _format_money(
    value: Decimal,
) -> str:
    formatted = f"{value:,.2f}"
    return (
        formatted
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _parse_reminder_days(
    value: str,
) -> list[int]:
    days: list[int] = []

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            day = int(item)
        except ValueError:
            continue

        if 1 <= day <= 30:
            days.append(day)

    return sorted(set(days))


def _serialize_preferences(
    preference: NotificationPreference,
) -> NotificationPreferenceRead:
    return NotificationPreferenceRead(
        due_soon_enabled=(
            preference.due_soon_enabled
        ),
        due_today_enabled=(
            preference.due_today_enabled
        ),
        overdue_enabled=(
            preference.overdue_enabled
        ),
        browser_notifications_enabled=(
            preference
            .browser_notifications_enabled
        ),
        reminder_days=_parse_reminder_days(
            preference.reminder_days_csv
        ),
    )


def get_or_create_preferences(
    db: Session,
    *,
    user_id: UUID,
) -> NotificationPreference:
    preference = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id
            == user_id,
        )
    )

    if preference is not None:
        return preference

    preference = NotificationPreference(
        user_id=user_id,
    )
    db.add(preference)
    db.flush()

    return preference


def get_preferences(
    db: Session,
    *,
    user_id: UUID,
) -> NotificationPreferenceRead:
    preference = get_or_create_preferences(
        db,
        user_id=user_id,
    )
    db.commit()

    return _serialize_preferences(
        preference
    )


def update_preferences(
    db: Session,
    *,
    user_id: UUID,
    payload: NotificationPreferenceUpdate,
) -> NotificationPreferenceRead:
    preference = get_or_create_preferences(
        db,
        user_id=user_id,
    )

    preference.due_soon_enabled = (
        payload.due_soon_enabled
    )
    preference.due_today_enabled = (
        payload.due_today_enabled
    )
    preference.overdue_enabled = (
        payload.overdue_enabled
    )
    preference.browser_notifications_enabled = (
        payload
        .browser_notifications_enabled
    )
    preference.reminder_days_csv = ",".join(
        str(day)
        for day in payload.reminder_days
    )

    db.commit()
    db.refresh(preference)

    sync_notifications(
        db,
        user_id=user_id,
    )

    return _serialize_preferences(
        preference
    )


def _notification_spec(
    transaction: Transaction,
    *,
    notification_type: NotificationType,
    severity: NotificationSeverity,
    title: str,
    message: str,
) -> dict[str, object]:
    return {
        "transaction_id": transaction.id,
        "fingerprint": (
            f"transaction:{transaction.id}:"
            f"{notification_type.value}:"
            f"{transaction.due_date.isoformat()}"
        ),
        "notification_type": (
            notification_type.value
        ),
        "severity": severity.value,
        "title": title,
        "message": message,
        "action_path": (
            f"/transactions/{transaction.id}"
        ),
        "due_date": transaction.due_date,
    }


def _build_specs(
    transactions: list[Transaction],
    preference: NotificationPreference,
) -> dict[str, dict[str, object]]:
    now = _now()
    today = now.date()
    reminder_days = _parse_reminder_days(
        preference.reminder_days_csv
    )
    specs: dict[
        str,
        dict[str, object],
    ] = {}

    for transaction in transactions:
        days_until = (
            transaction.due_date - today
        ).days
        money = _format_money(
            transaction.amount
        )

        spec: dict[str, object] | None = None

        if (
            days_until < 0
            and preference.overdue_enabled
        ):
            overdue_days = abs(days_until)
            spec = _notification_spec(
                transaction,
                notification_type=(
                    NotificationType.OVERDUE
                ),
                severity=(
                    NotificationSeverity.DANGER
                ),
                title="Movimentação atrasada",
                message=(
                    f"{transaction.description} "
                    f"(R$ {money}) venceu há "
                    f"{overdue_days} "
                    f"{'dia' if overdue_days == 1 else 'dias'}."
                ),
            )
        elif (
            days_until == 0
            and preference.due_today_enabled
        ):
            spec = _notification_spec(
                transaction,
                notification_type=(
                    NotificationType.DUE_TODAY
                ),
                severity=(
                    NotificationSeverity.WARNING
                ),
                title="Vence hoje",
                message=(
                    f"{transaction.description} "
                    f"(R$ {money}) vence hoje."
                ),
            )
        elif (
            days_until > 0
            and preference.due_soon_enabled
            and days_until in reminder_days
        ):
            spec = _notification_spec(
                transaction,
                notification_type=(
                    NotificationType.DUE_SOON
                ),
                severity=(
                    NotificationSeverity.INFO
                ),
                title="Vencimento próximo",
                message=(
                    f"{transaction.description} "
                    f"(R$ {money}) vence em "
                    f"{days_until} "
                    f"{'dia' if days_until == 1 else 'dias'}."
                ),
            )

        if spec is not None:
            specs[
                str(spec["fingerprint"])
            ] = spec

    return specs


def sync_notifications(
    db: Session,
    *,
    user_id: UUID,
) -> NotificationSyncRead:
    preference = get_or_create_preferences(
        db,
        user_id=user_id,
    )
    now = _now()
    today = now.date()
    reminder_days = _parse_reminder_days(
        preference.reminder_days_csv
    )
    maximum_days = max(
        reminder_days,
        default=0,
    )

    transactions = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id
                == user_id,
                Transaction.status
                == TransactionStatus.PENDING,
                Transaction.due_date
                <= today
                + timedelta(
                    days=maximum_days
                ),
            )
            .order_by(
                Transaction.due_date.asc(),
            )
            .limit(1000)
        )
    )

    specs = _build_specs(
        transactions,
        preference,
    )
    fingerprints = set(specs)

    existing = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id
                == user_id,
                Notification.fingerprint
                .in_(fingerprints)
                if fingerprints
                else False,
            )
        )
    )
    existing_by_fingerprint = {
        notification.fingerprint:
            notification
        for notification in existing
    }

    synchronized = 0

    for fingerprint, spec in specs.items():
        notification = (
            existing_by_fingerprint.get(
                fingerprint
            )
        )

        if notification is None:
            notification = Notification(
                user_id=user_id,
                **spec,
            )
            db.add(notification)
            synchronized += 1
            continue

        notification.transaction_id = (
            spec["transaction_id"]
        )
        notification.notification_type = (
            str(spec["notification_type"])
        )
        notification.severity = str(
            spec["severity"]
        )
        notification.title = str(
            spec["title"]
        )
        notification.message = str(
            spec["message"]
        )
        notification.action_path = (
            str(spec["action_path"])
        )
        notification.due_date = (
            spec["due_date"]
        )

    stale_query = select(
        Notification
    ).where(
        Notification.user_id == user_id,
        Notification.notification_type
        .in_(GENERATED_TYPES),
        Notification.dismissed_at.is_(None),
        Notification.read_at.is_(None),
    )

    if fingerprints:
        stale_query = stale_query.where(
            Notification.fingerprint
            .not_in(fingerprints)
        )

    stale_notifications = list(
        db.scalars(stale_query)
    )

    for notification in stale_notifications:
        notification.dismissed_at = now

    db.commit()

    unread_count = _count_unread(
        db,
        user_id=user_id,
    )

    return NotificationSyncRead(
        synchronized=synchronized,
        unread_count=unread_count,
    )


def _visible_filter(
    *,
    now: datetime,
):
    return (
        Notification.dismissed_at.is_(None),
        or_(
            Notification.snoozed_until
            .is_(None),
            Notification.snoozed_until
            <= now,
        ),
    )


def _count_unread(
    db: Session,
    *,
    user_id: UUID,
) -> int:
    now = _now()

    return len(
        list(
            db.scalars(
                select(Notification.id)
                .where(
                    Notification.user_id
                    == user_id,
                    Notification.read_at
                    .is_(None),
                    *_visible_filter(
                        now=now
                    ),
                )
                .limit(1000)
            )
        )
    )


def get_unread_count(
    db: Session,
    *,
    user_id: UUID,
) -> NotificationCountRead:
    sync_notifications(
        db,
        user_id=user_id,
    )

    return NotificationCountRead(
        unread_count=_count_unread(
            db,
            user_id=user_id,
        )
    )


def list_notifications(
    db: Session,
    *,
    user_id: UUID,
    unread_only: bool,
    limit: int,
    offset: int,
) -> NotificationListRead:
    sync_notifications(
        db,
        user_id=user_id,
    )
    now = _now()

    query = select(Notification).where(
        Notification.user_id == user_id,
        *_visible_filter(now=now),
    )

    if unread_only:
        query = query.where(
            Notification.read_at.is_(None)
        )

    items = list(
        db.scalars(
            query
            .order_by(
                Notification.read_at
                .is_not(None),
                Notification.created_at
                .desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )

    return NotificationListRead(
        items=[
            NotificationRead.model_validate(
                item
            )
            for item in items
        ],
        unread_count=_count_unread(
            db,
            user_id=user_id,
        ),
    )


def _owned_notification(
    db: Session,
    *,
    notification_id: UUID,
    user_id: UUID,
) -> Notification:
    notification = db.scalar(
        select(Notification).where(
            Notification.id
            == notification_id,
            Notification.user_id
            == user_id,
        )
    )

    if notification is None:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail="Notificação não encontrada.",
        )

    return notification


def mark_as_read(
    db: Session,
    *,
    notification_id: UUID,
    user_id: UUID,
) -> NotificationRead:
    notification = _owned_notification(
        db,
        notification_id=notification_id,
        user_id=user_id,
    )

    if notification.read_at is None:
        notification.read_at = _now()

    db.commit()
    db.refresh(notification)

    return NotificationRead.model_validate(
        notification
    )


def mark_all_as_read(
    db: Session,
    *,
    user_id: UUID,
) -> NotificationCountRead:
    now = _now()
    notifications = list(
        db.scalars(
            select(Notification).where(
                Notification.user_id
                == user_id,
                Notification.read_at
                .is_(None),
                *_visible_filter(now=now),
            )
        )
    )

    for notification in notifications:
        notification.read_at = now

    db.commit()

    return NotificationCountRead(
        unread_count=0
    )


def dismiss_notification(
    db: Session,
    *,
    notification_id: UUID,
    user_id: UUID,
) -> None:
    notification = _owned_notification(
        db,
        notification_id=notification_id,
        user_id=user_id,
    )
    notification.dismissed_at = _now()
    db.commit()


def snooze_notification(
    db: Session,
    *,
    notification_id: UUID,
    user_id: UUID,
    days: int,
) -> NotificationRead:
    notification = _owned_notification(
        db,
        notification_id=notification_id,
        user_id=user_id,
    )
    notification.snoozed_until = (
        _now() + timedelta(days=days)
    )
    db.commit()
    db.refresh(notification)

    return NotificationRead.model_validate(
        notification
    )
