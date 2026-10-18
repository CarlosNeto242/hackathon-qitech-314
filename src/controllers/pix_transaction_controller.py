from datetime import datetime
from typing import List, Tuple

from sqlalchemy.exc import IntegrityError

from constants import BANK_ISPB
from controllers.base_controller import BaseController
from dtos import PixTransactionDTO
from errors import (
    AccountDataMismatch,
    InvalidDateTime,
    InvalidPixDocumentNumber,
    NotFoundPixTransaction,
)
from models import Account, PixTransaction
from repositories import AccountRepository, PixTransactionRepository
from utils.document_number import is_valid_document, only_digits

PIX_ID_UNIQUE_CONSTRAINT = "transaction_pix_id_key"


class PixTransactionController(BaseController):
    """O motor antifraude: recebe um Pix, decide e grava."""

    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)
        self.pix_transaction_repository = PixTransactionRepository(self.context)

    def analyze(self, payload: dict) -> Tuple[dict, bool]:

        pix_id = payload["id"]

        existing = self.pix_transaction_repository.get_by_pix_id(pix_id)
        if existing is not None:
            return PixTransactionDTO.obj_to_dict(existing), False

        transaction_date = self._parse_datetime(payload["transaction_date"], "transaction_date")
        source_account_data = self._account_data(payload["source_account"], "source_account", BANK_ISPB)
        destination_account_data = self._account_data(
            payload["destination_account"],
            "destination_account",
            payload["destination_account"]["participant"],
        )

        source_account = self._register_account(source_account_data, "source_account")
        destination_account = self._register_account(destination_account_data, "destination_account")

        status, decision_reasons = self._decide(source_account, destination_account)

        geolocation = payload["source"].get("geolocation") or {}
        transaction_data = {
            "pix_id": pix_id,
            "amount": payload["amount"],
            "transaction_date": transaction_date,
            "source_account_id": source_account.id,
            "destination_account_id": destination_account.id,
            "device_id": payload["source"]["device_id"],
            "channel": payload["source"]["channel"],
            "ip": payload["source"]["ip"],
            "latitude": geolocation.get("latitude"),
            "longitude": geolocation.get("longitude"),
        }
        pix_transaction = self.pix_transaction_repository.create(transaction_data, status, decision_reasons)

        try:
            self.session.commit()
        except IntegrityError as error:

            self.session.rollback()
            if self._constraint_name(error) != PIX_ID_UNIQUE_CONSTRAINT:
                raise

            existing = self.pix_transaction_repository.get_by_pix_id(pix_id)
            return PixTransactionDTO.obj_to_dict(existing), False

        return PixTransactionDTO.obj_to_dict(pix_transaction), True

    def get_by_pix_id(self, pix_id: str) -> dict:
        pix_transaction = self.pix_transaction_repository.get_by_pix_id(pix_id)
        if pix_transaction is None:
            raise NotFoundPixTransaction(pix_id)

        return PixTransactionDTO.obj_to_dict(pix_transaction)

    def _decide(self, source_account: Account, destination_account: Account) -> Tuple[str, List[str]]:

        # Aqui mora as nossas regras de negocio

        if Account.PROHIBITED in (source_account.status, destination_account.status):
            return PixTransaction.REJECTED, [PixTransaction.ACCOUNT_BLOCKED]

        return PixTransaction.APPROVED, []

    def _register_account(self, account_data: dict, field: str) -> Account:

        account = self.account_repository.get_or_create(account_data)

        divergent_fields = []
        if account.document_number != account_data["document_number"]:
            divergent_fields.append("document_number")
        if account.opening_date != account_data["opening_date"]:
            divergent_fields.append("opening_date")

        if divergent_fields:

            self.logger.warning(
                f"Divergencia de dados em {field} (account.id={account.id}): {', '.join(divergent_fields)}"
            )
            raise AccountDataMismatch()

        return account

    def _account_data(self, raw_account: dict, field: str, participant: str) -> dict:

        document_number = raw_account["owner"]["document_number"]
        if not is_valid_document(document_number):
            raise InvalidPixDocumentNumber(f"{field}.owner.document_number")

        return {
            "participant": participant,
            "branch": raw_account["branch"],
            "account_number": raw_account["account_number"],
            "opening_date": self._parse_datetime(raw_account["opening_date"], f"{field}.opening_date"),
            "document_number": only_digits(document_number),
        }

    def _parse_datetime(self, raw_value: str, field: str) -> datetime:

        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            raise InvalidDateTime(field)

    def _constraint_name(self, error: IntegrityError) -> str:
        diag = getattr(error.orig, "diag", None)
        return getattr(diag, "constraint_name", None)
