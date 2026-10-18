from typing import List, Optional
from uuid import uuid4

from database import Context
from models import PixTransaction


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
