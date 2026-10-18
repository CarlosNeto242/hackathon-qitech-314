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
