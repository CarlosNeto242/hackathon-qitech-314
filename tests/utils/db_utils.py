from os import environ
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from tests.utils.request_generator import BANK_ISPB


RESET_QUERIES = [
    "DROP SCHEMA public CASCADE;",
    "CREATE SCHEMA public;",
    "GRANT ALL ON SCHEMA public TO CURRENT_USER;",
    "GRANT ALL ON SCHEMA public TO public;",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = PROJECT_ROOT / "database" / "database.sql"

DEFAULT_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@localhost:5432/bootcamp"

DATABASE_OFFLINE = (
    "Não consegui falar com o banco em {host}:{port}.\n"
    "Ele precisa estar de pé pros testes rodarem. Suba com:  docker compose up\n"
    "Se ele já está de pé, confira a porta na DATABASE_URL do seu .env."
)


SEED_TRANSACTIONS = """
    INSERT INTO transaction (pix_id, payload_hash, transaction_key, amount, transaction_date, created_at,
                             source_account_id, destination_account_id, device_id, channel, ip, status)
    SELECT 'seed-' || substr(md5(random()::text), 1, 11), encode(sha256(random()::text::bytea), 'hex'),
           gen_random_uuid(), :amount,
           now() - make_interval(days => :days_ago), now() - make_interval(days => :days_ago),
           (SELECT id FROM account WHERE participant = :source_participant AND branch = :source_branch AND account_number = :source_account_number),
           (SELECT id FROM account WHERE participant = :destination_participant AND branch = :destination_branch AND account_number = :destination_account_number),
           :device_id, 'app', '127.0.0.1', 'approved'
    FROM generate_series(1, :count)
    RETURNING id
"""

SEED_FROM_DISTINCT_PAYERS = """
    WITH payers AS (
        INSERT INTO account (participant, branch, account_number, opening_date, document_number)
        SELECT '32402502', '9999', 'seed' || substr(md5(random()::text), 1, 12), now() - interval '400 days',
               lpad(floor(random() * 1e11)::bigint::text, 11, '0')
        FROM generate_series(1, :count)
        RETURNING id
    )
    INSERT INTO transaction (pix_id, payload_hash, transaction_key, amount, transaction_date, created_at,
                             source_account_id, destination_account_id, device_id, channel, ip, status)
    SELECT 'seed-' || substr(md5(random()::text), 1, 11), encode(sha256(random()::text::bytea), 'hex'),
           gen_random_uuid(), :amount,
           now() - make_interval(mins => :minutes_ago), now() - make_interval(mins => :minutes_ago),
           payers.id, (SELECT id FROM account WHERE participant = :destination_participant AND branch = :destination_branch AND account_number = :destination_account_number), 'dvc-seed', 'app', '127.0.0.1', 'approved'
    FROM payers
    RETURNING id
"""


class DbUtils:
    @staticmethod
    def database_url() -> str:
        return environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

    @staticmethod
    def rollback() -> None:
        engine = create_engine(DbUtils.database_url(), isolation_level="AUTOCOMMIT")

        try:
            with engine.connect() as connection:
                for query in RESET_QUERIES:
                    connection.exec_driver_sql(query)

                connection.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))
        except OperationalError:
            message = DATABASE_OFFLINE.format(host=engine.url.host, port=engine.url.port)
            raise RuntimeError(message) from None
        finally:
            engine.dispose()

    @staticmethod
    def _execute(query: str, params: dict) -> list:
        engine = create_engine(DbUtils.database_url(), isolation_level="AUTOCOMMIT")

        try:
            with engine.connect() as connection:
                return connection.execute(text(query), params).fetchall()
        except OperationalError:
            message = DATABASE_OFFLINE.format(host=engine.url.host, port=engine.url.port)
            raise RuntimeError(message) from None
        finally:
            engine.dispose()

    @staticmethod
    def seed_sent(
        source_account: dict,
        destination_account: dict,
        count: int,
        amount: int,
        days_ago: int,
        device_id: str,
    ) -> None:
        DbUtils._execute(
            SEED_TRANSACTIONS,
            {
                "count": count,
                "amount": amount,
                "days_ago": days_ago,
                "device_id": device_id,
                **DbUtils._identity("source", source_account, BANK_ISPB),
                **DbUtils._identity("destination", destination_account, destination_account["participant"]),
            },
        )

    @staticmethod
    def seed_received_from_distinct_payers(
        destination_account: dict, count: int, amount: int, minutes_ago: int
    ) -> None:
        DbUtils._execute(
            SEED_FROM_DISTINCT_PAYERS,
            {
                "count": count,
                "amount": amount,
                "minutes_ago": minutes_ago,
                **DbUtils._identity("destination", destination_account, destination_account["participant"]),
            },
        )

    @staticmethod
    def _identity(role: str, account: dict, participant: str) -> dict:
        return {
            f"{role}_participant": participant,
            f"{role}_branch": account["branch"],
            f"{role}_account_number": account["account_number"],
        }
