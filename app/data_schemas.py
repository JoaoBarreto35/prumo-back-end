from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    model_validator,
)


class DataImportFormat(StrEnum):
    PRUMO_BACKUP = "prumo_backup"
    CSV = "csv"


class DataImportMode(StrEnum):
    MERGE = "merge"
    REPLACE = "replace"


class DataExportFile(BaseModel):
    filename: str
    mime_type: str
    content: str


class DataSummaryRead(BaseModel):
    accounts: int
    categories: int
    groups: int
    transactions: int
    closings: int
    planning_scenarios: int
    lume_conversations: int
    first_transaction_date: str | None
    last_transaction_date: str | None


class DataImportRequest(BaseModel):
    data_format: DataImportFormat
    content: str = Field(
        min_length=1,
        max_length=20_000_000,
    )
    filename: str | None = Field(
        default=None,
        max_length=255,
    )
    mode: DataImportMode = (
        DataImportMode.MERGE
    )
    skip_duplicates: bool = True
    create_missing_structure: bool = (
        True
    )
    confirm_replace: bool = False
    current_password: str | None = Field(
        default=None,
        max_length=128,
    )

class DataImportApplyRequest(
    DataImportRequest,
):
    @model_validator(mode="after")
    def validate_replace(
        self,
    ):
        if (
            self.mode
            == DataImportMode.REPLACE
            and not self.confirm_replace
        ):
            raise ValueError(
                "Confirme a substituição "
                "dos dados atuais."
            )

        if (
            self.mode
            == DataImportMode.REPLACE
            and not self.current_password
        ):
            raise ValueError(
                "Informe a senha atual "
                "para substituir os dados."
            )

        return self


class DataImportCounts(BaseModel):
    accounts: int = 0
    categories: int = 0
    groups: int = 0
    transactions: int = 0
    closings: int = 0
    planning_scenarios: int = 0
    lume_conversations: int = 0
    lume_messages: int = 0
    preferences: int = 0


class DataImportPreviewRead(BaseModel):
    data_format: DataImportFormat
    mode: DataImportMode
    valid: bool
    source_version: int | None
    counts: DataImportCounts
    duplicates: DataImportCounts
    will_create: DataImportCounts
    warnings: list[str]
    errors: list[str]
    sample: list[dict[str, Any]]


class DataImportResultRead(BaseModel):
    message: str
    created: DataImportCounts
    skipped: DataImportCounts
    warnings: list[str]


class ClearFinancialDataInput(BaseModel):
    current_password: str = Field(
        min_length=1,
        max_length=128,
    )
    confirmation: str

    @model_validator(mode="after")
    def validate_confirmation(
        self,
    ):
        if (
            self.confirmation
            != "APAGAR MEUS DADOS"
        ):
            raise ValueError(
                "Digite exatamente "
                "APAGAR MEUS DADOS."
            )

        return self


class DeleteAccountInput(BaseModel):
    current_password: str = Field(
        min_length=1,
        max_length=128,
    )
    email: EmailStr
    confirmation: str

    @model_validator(mode="after")
    def validate_confirmation(
        self,
    ):
        if (
            self.confirmation
            != "EXCLUIR MINHA CONTA"
        ):
            raise ValueError(
                "Digite exatamente "
                "EXCLUIR MINHA CONTA."
            )

        return self


class DataOperationLogRead(BaseModel):
    id: UUID
    action: str
    data_format: str
    status: str
    summary: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class DataMessageRead(BaseModel):
    message: str
