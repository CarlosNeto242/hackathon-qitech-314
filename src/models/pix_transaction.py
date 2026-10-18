from sqlalchemy import BigInteger, Column, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, INET, UUID

from models.base import Base
from models.account import Account


class PixTransaction(Base):

    __tablename__ = "transaction"

    APPROVED = "approved"
    REJECTED = "rejected"
    TWO_FACTOR_REQUIRED = "two_factor_required"

    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    DEST_FRAUD_MARKED = "DEST_FRAUD_MARKED"
    DEST_RECEIVING_VELOCITY = "DEST_RECEIVING_VELOCITY"
    DEST_NEW_ACCOUNT = "DEST_NEW_ACCOUNT"
    DEST_HIGH_AMOUNT = "DEST_HIGH_AMOUNT"
    SRC_HIGH_AMOUNT = "SRC_HIGH_AMOUNT"
    SRC_SENDING_VELOCITY = "SRC_SENDING_VELOCITY"
    SRC_NEW_DEVICE = "SRC_NEW_DEVICE"
    SRC_LOCATION_MISMATCH = "SRC_LOCATION_MISMATCH"

    id = Column(Integer, primary_key=True)
    pix_id = Column(String(16), nullable=False)
    # SHA-256 do payload recebido: o mesmo pix_id com outro conteúdo é conflito.
    payload_hash = Column(String(64), nullable=False)
    transaction_key = Column(UUID(as_uuid=False), nullable=False)
    amount = Column(BigInteger, nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source_account_id = Column(Integer, ForeignKey(Account.id), nullable=False)
    destination_account_id = Column(Integer, ForeignKey(Account.id), nullable=False)
    device_id = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    ip = Column(INET, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(
        Enum(APPROVED, REJECTED, TWO_FACTOR_REQUIRED, name="transaction_status"),
        nullable=False,
    )
    decision_reasons = Column(
        ARRAY(
            Enum(
                ACCOUNT_BLOCKED,
                DEST_FRAUD_MARKED,
                DEST_RECEIVING_VELOCITY,
                DEST_NEW_ACCOUNT,
                DEST_HIGH_AMOUNT,
                SRC_HIGH_AMOUNT,
                SRC_SENDING_VELOCITY,
                SRC_NEW_DEVICE,
                SRC_LOCATION_MISMATCH,
                name="decision_reason",
            )
        ),
        nullable=False,
        server_default="{}",
    )

    __table_args__ = (
        UniqueConstraint("pix_id"),
        UniqueConstraint("transaction_key"),
    )
