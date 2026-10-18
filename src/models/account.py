from sqlalchemy import Column, DateTime, Enum, Integer, String, UniqueConstraint, func

from models.base import Base


class Account(Base):
    __tablename__ = "account"

    PERMITTED = "PERMITTED"
    PROHIBITED = "PROHIBITED"

    id = Column(Integer, primary_key=True)
    participant = Column(String(8), nullable=False)
    branch = Column(String(10), nullable=False)
    account_number = Column(String(20), nullable=False)
    opening_date = Column(DateTime(timezone=True), nullable=False)
    document_number = Column(String(14), nullable=False)
    status = Column(Enum(PERMITTED, PROHIBITED, name="account_status"), nullable=False, server_default=PERMITTED)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("participant", "branch", "account_number"),)
