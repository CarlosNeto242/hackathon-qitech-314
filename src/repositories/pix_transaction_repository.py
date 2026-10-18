from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import func

from database import Context
from models import Account, PixTransaction


class PixTransactionRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create(self, transaction_data: dict, status: str, decision_reasons: List[str]) -> PixTransaction:
        pix_transaction = PixTransaction(**transaction_data)
        pix_transaction.transaction_key = str(uuid4())
        pix_transaction.status = status
        pix_transaction.decision_reasons = decision_reasons

        self.session.add(pix_transaction)
        return pix_transaction

    def get_by_pix_id(self, pix_id: str) -> Optional[PixTransaction]:
        return self.session.query(PixTransaction).filter(PixTransaction.pix_id == pix_id).first()

    def count_received_by_document_since(self, document_number: str, since: datetime) -> int:
        return (
            self.session.query(func.count(PixTransaction.id))
            .join(Account, Account.id == PixTransaction.destination_account_id)
            .filter(Account.document_number == document_number, PixTransaction.created_at > since)
            .scalar()
        )

    def count_received_between(self, account_id: int, start: datetime, end: datetime) -> int:
        return (
            self.session.query(func.count(PixTransaction.id))
            .filter(
                PixTransaction.destination_account_id == account_id,
                PixTransaction.created_at > start,
                PixTransaction.created_at <= end,
            )
            .scalar()
        )

    def sum_received_between(self, account_id: int, start: datetime, end: datetime) -> int:
        return (
            self.session.query(func.coalesce(func.sum(PixTransaction.amount), 0))
            .filter(
                PixTransaction.destination_account_id == account_id,
                PixTransaction.created_at > start,
                PixTransaction.created_at <= end,
            )
            .scalar()
        )

    def count_distinct_payers(self, account_id: int, excluding_account_id: int) -> int:
        return (
            self.session.query(func.count(func.distinct(PixTransaction.source_account_id)))
            .filter(
                PixTransaction.destination_account_id == account_id,
                PixTransaction.source_account_id != excluding_account_id,
            )
            .scalar()
        )

    def count_sent_between(self, account_id: int, start: datetime, end: datetime) -> int:
        return (
            self.session.query(func.count(PixTransaction.id))
            .filter(
                PixTransaction.source_account_id == account_id,
                PixTransaction.created_at > start,
                PixTransaction.created_at <= end,
            )
            .scalar()
        )

    def count_accepted_sent_since(self, account_id: int, since: datetime) -> int:
        return (
            self.session.query(func.count(PixTransaction.id))
            .filter(
                PixTransaction.source_account_id == account_id,
                PixTransaction.status.in_([PixTransaction.APPROVED, PixTransaction.TWO_FACTOR_REQUIRED]),
                PixTransaction.created_at > since,
            )
            .scalar()
        )

    def accepted_sent_amount_percentile(self, account_id: int, since: datetime, percentile: float) -> Optional[float]:
        return (
            self.session.query(func.percentile_cont(percentile).within_group(PixTransaction.amount.asc()))
            .filter(
                PixTransaction.source_account_id == account_id,
                PixTransaction.status.in_([PixTransaction.APPROVED, PixTransaction.TWO_FACTOR_REQUIRED]),
                PixTransaction.created_at > since,
            )
            .scalar()
        )

    def device_recognized(self, account_id: int, device_id: str) -> bool:
        return (
            self.session.query(PixTransaction.id)
            .filter(
                PixTransaction.source_account_id == account_id,
                PixTransaction.device_id == device_id,
                PixTransaction.status.in_([PixTransaction.APPROVED, PixTransaction.TWO_FACTOR_REQUIRED]),
            )
            .first()
            is not None
        )

    def last_located_sent(self, account_id: int, device_id: Optional[str] = None) -> Optional[PixTransaction]:
        query = self.session.query(PixTransaction).filter(
            PixTransaction.source_account_id == account_id,
            PixTransaction.latitude.isnot(None),
            PixTransaction.status.in_([PixTransaction.APPROVED, PixTransaction.TWO_FACTOR_REQUIRED]),
        )
        if device_id is not None:
            query = query.filter(PixTransaction.device_id == device_id)
        return query.order_by(PixTransaction.created_at.desc()).first()

    def last_transactions_as_destination(self, account_id: int, since: datetime, limit: int) -> List[PixTransaction]:
        return (
            self.session.query(PixTransaction)
            .filter(PixTransaction.destination_account_id == account_id, PixTransaction.created_at > since)
            .order_by(PixTransaction.created_at.desc())
            .limit(limit)
            .all()
        )

    def last_transactions_as_source(self, account_id: int, since: datetime, limit: int) -> List[PixTransaction]:
        return (
            self.session.query(PixTransaction)
            .filter(PixTransaction.source_account_id == account_id, PixTransaction.created_at > since)
            .order_by(PixTransaction.created_at.desc())
            .limit(limit)
            .all()
        )
