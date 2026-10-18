from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

from database import Context
from models import Account, AccountEvent


class AccountRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def get_or_create(self, account_data: dict) -> Account:
        statement = (
            insert(Account)
            .values(**account_data)
            .on_conflict_do_nothing(index_elements=["participant", "branch", "account_number"])
        )
        self.session.execute(statement)

        return self.get_by_identity(
            account_data["participant"],
            account_data["branch"],
            account_data["account_number"],
        )

    def get_by_identity(self, participant: str, branch: str, account_number: str) -> Optional[Account]:
        return (
            self.session.query(Account)
            .filter(
                Account.participant == participant,
                Account.branch == branch,
                Account.account_number == account_number,
            )
            .first()
        )

    def get_by_identity_for_update(self, participant: str, branch: str, account_number: str) -> Optional[Account]:
        return (
            self.session.query(Account)
            .filter(
                Account.participant == participant,
                Account.branch == branch,
                Account.account_number == account_number,
            )
            .with_for_update()
            .first()
        )

    def get_by_id_for_update(self, account_id: int) -> Optional[Account]:
        return self.session.query(Account).filter(Account.id == account_id).with_for_update().first()

    def update_status(
        self,
        account: Account,
        new_status: str,
        reason: str,
        transaction_id: Optional[int] = None,
    ) -> None:
        event = AccountEvent()
        event.account_id = account.id
        event.transaction_id = transaction_id
        event.from_status = account.status
        event.to_status = new_status
        event.reason = reason

        account.status = new_status
        self.session.add(event)

    def last_unblock_at(self, account_id: int) -> Optional[datetime]:
        return (
            self.session.query(func.max(AccountEvent.created_at))
            .filter(AccountEvent.account_id == account_id, AccountEvent.reason == AccountEvent.MANUAL_UNBLOCK)
            .scalar()
        )

    def lock_accounts(self, account_ids: List[int]) -> None:
        (
            self.session.query(Account.id)
            .filter(Account.id.in_(account_ids))
            .order_by(Account.id)
            .with_for_update()
            .all()
        )

    def lock_document(self, document_number: str) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:document_number))"),
            {"document_number": document_number},
        )
