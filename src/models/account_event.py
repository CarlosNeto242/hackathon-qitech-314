from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, func

from models.base import Base
from models.account import Account
from models.pix_transaction import PixTransaction


class AccountEvent(Base):
    __tablename__ = "events"

    REPEATED_RISK_REJECTIONS_DEST = "REPEATED_RISK_REJECTIONS_DEST"
    REPEATED_RISK_REJECTIONS_SRC = "REPEATED_RISK_REJECTIONS_SRC"
    MANUAL_UNBLOCK = "MANUAL_UNBLOCK"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey(Account.id), nullable=False)
    transaction_id = Column(Integer, ForeignKey(PixTransaction.id), nullable=True)
    from_status = Column(Enum(Account.PERMITTED, Account.PROHIBITED, name="account_status"), nullable=False)
    to_status = Column(Enum(Account.PERMITTED, Account.PROHIBITED, name="account_status"), nullable=False)
    reason = Column(Enum(REPEATED_RISK_REJECTIONS_DEST, REPEATED_RISK_REJECTIONS_SRC, MANUAL_UNBLOCK, name="account_event_reason"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
