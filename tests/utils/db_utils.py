from os import environ
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


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
                             source_account_id, destination_account_id, device_id, channel, ip, status,
                             decision_reasons, latitude, longitude)
    SELECT 'seed-' || substr(md5(random()::text), 1, 11), encode(sha256(random()::text::bytea), 'hex'),
           gen_random_uuid(), :amount,
           now() - make_interval(mins => :minutes_ago), now() - make_interval(mins => :minutes_ago),
           :source, :destination, :device_id, 'app', '127.0.0.1',
           CAST(:status AS transaction_status), CAST(:reasons AS decision_reason[]),
           CAST(:latitude AS double precision), CAST(:longitude AS double precision)
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
           payers.id, :destination, 'dvc-seed', 'app', '127.0.0.1', 'approved'
    FROM payers
    RETURNING id
"""


class DbUtils:
    """Apaga o banco inteiro e o recria do zero — quando alguém chama.

    Não existe limpeza automática neste projeto. O `rollback()` roda no
    teste que o chamar, na linha em que for chamado, e em mais lugar
    nenhum. Todos os testes dividem o mesmo banco, e cada um enxerga o
    que os anteriores deixaram pra trás.

    O nome engana um pouco: isto não desfaz uma transação. Ele derruba
    o schema `public` com tudo que estiver dentro e roda o
    `database/database.sql` de novo — tabelas vazias e os quatro status
    do INSERT de volta.

    Quando o seu teste precisa chamar: sempre que alguma asserção
    depender de QUANTAS linhas existem no banco — contar, listar,
    paginar, filtrar. Nesses casos `DbUtils.rollback()` é a primeira
    linha do teste, antes de criar qualquer coisa (o exemplo está em
    `tests/integration/pix_transaction/test_admin_unblock.py`). Um teste que só olha
    as entidades que ele mesmo criou, pela chave que recebeu de volta,
    não precisa de limpeza nenhuma — e fica mais rápido sem ela.

    A limpeza acontece pela mesma conexão que a aplicação usa (a
    DATABASE_URL), e não por um programa externo: quem tem Docker
    rodando já tem tudo que precisa.
    """

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
    def block_account(branch: str, account_number: str) -> int:
        """Bloqueia uma conta direto no banco e devolve o id dela.

        É uma exceção à regra de montar cenário só pela API, e ela tem
        prazo: hoje nenhuma rota bloqueia conta, porque o bloqueio só vai
        nascer da reincidência. Quando ela existir, os testes passam a
        bloquear repetindo Pix rejeitados, e este método pode sair.
        """
        rows = DbUtils._execute(
            "UPDATE account SET status = 'PROHIBITED' "
            "WHERE branch = :branch AND account_number = :account_number RETURNING id",
            {"branch": branch, "account_number": account_number},
        )
        assert len(rows) == 1, f"esperava uma conta {branch}/{account_number}, achei {len(rows)}"
        return rows[0].id

    @staticmethod
    def account_events(account_id: int) -> list:
        """Os eventos de status da conta, do mais antigo pro mais novo.

        A API não expõe a tabela events, então é por aqui que o teste
        confere que o desbloqueio deixou o rastro certo.
        """
        return DbUtils._execute(
            "SELECT from_status, to_status, reason, transaction_id FROM events "
            "WHERE account_id = :account_id ORDER BY created_at, id",
            {"account_id": account_id},
        )

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
    def account_id(branch: str, account_number: str) -> int:
        rows = DbUtils._execute(
            "SELECT id FROM account WHERE branch = :branch AND account_number = :account_number",
            {"branch": branch, "account_number": account_number},
        )
        assert len(rows) == 1, f"esperava uma conta {branch}/{account_number}, achei {len(rows)}"
        return rows[0].id

    @staticmethod
    def transaction_id(pix_id: str) -> int:
        return DbUtils._execute("SELECT id FROM transaction WHERE pix_id = :pix_id", {"pix_id": pix_id})[0].id

    # ─── Semeadura de histórico ─────────────────────────────────────────
    #
    # Pela API, todo Pix nasce com o horário de AGORA: não dá pra criar um
    # histórico de 10 dias atrás sem esperar 10 dias. As regras que olham o
    # passado (perfil de valor, média do CNPJ, pagadores de conta nova) só são
    # testáveis com o histórico plantado direto no banco. O resto da jornada
    # (o Pix que é decidido) continua passando pela API.

    @staticmethod
    def seed_sent(
        source_account_id: int,
        destination_account_id: int,
        count: int,
        amount: int,
        device_id: str,
        days_ago: int = 0,
        minutes_ago: int = 0,
        two_factor_reason: str = None,
        geolocation: dict = None,
    ) -> None:
        """`count` Pix enviados pela conta, `days_ago` dias e `minutes_ago`
        minutos atrás. Aprovados; com `two_factor_reason`, com 2FA por esse
        motivo."""
        DbUtils._execute(
            SEED_TRANSACTIONS,
            {
                "count": count,
                "amount": amount,
                "minutes_ago": days_ago * 24 * 60 + minutes_ago,
                "source": source_account_id,
                "destination": destination_account_id,
                "device_id": device_id,
                "status": "two_factor_required" if two_factor_reason else "approved",
                "reasons": "{" + two_factor_reason + "}" if two_factor_reason else "{}",
                "latitude": geolocation["latitude"] if geolocation else None,
                "longitude": geolocation["longitude"] if geolocation else None,
            },
        )

    @staticmethod
    def seed_received_from_distinct_payers(
        destination_account_id: int, count: int, amount: int, minutes_ago: int
    ) -> None:
        """`count` Pix aprovados recebidos pela conta, cada um de uma conta
        pagadora diferente (criada aqui), `minutes_ago` minutos atrás."""
        DbUtils._execute(
            SEED_FROM_DISTINCT_PAYERS,
            {
                "count": count,
                "amount": amount,
                "minutes_ago": minutes_ago,
                "destination": destination_account_id,
            },
        )

    @staticmethod
    def age_transaction(pix_id: str, days: int) -> None:
        """Empurra um Pix já analisado `days` dias pro passado.

        Serve pra montar um cliente "antigo": o Pix que registrou a conta e o
        aparelho aconteceu agora, mas na história do teste ele é de dias atrás,
        e não pode contar nas janelas de velocidade da rotina que vem depois.
        """
        DbUtils._execute(
            "UPDATE transaction SET created_at = created_at - make_interval(days => :days) "
            "WHERE pix_id = :pix_id RETURNING id",
            {"pix_id": pix_id, "days": days},
        )

    @staticmethod
    def age_received(account_id: int, days: int) -> None:
        """Empurra todos os Pix recebidos pela conta `days` dias pro passado,
        pra encenar algo que aconteceu antes (fora das janelas de velocidade)."""
        DbUtils._execute(
            "UPDATE transaction SET created_at = created_at - make_interval(days => :days) "
            "WHERE destination_account_id = :account_id RETURNING id",
            {"account_id": account_id, "days": days},
        )
