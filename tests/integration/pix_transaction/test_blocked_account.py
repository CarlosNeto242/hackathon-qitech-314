from copy import deepcopy

from tests.utils import DbUtils, PayloadGenerator, RequestGenerator


def registra_e_bloqueia(papel: str) -> tuple:
    """Registra as contas com um Pix aprovado e bloqueia a do `papel` pedido.

    Devolve o primeiro payload (pra reaproveitar as contas) e o id da conta
    bloqueada.
    """
    primeiro = PayloadGenerator.create_pix_transaction_payload()
    status, response = RequestGenerator.POST_pix_transaction(primeiro)
    assert status == 201
    assert response["status"] == "approved"

    conta = primeiro[papel]
    account_id = DbUtils.block_account(conta["branch"], conta["account_number"])
    return primeiro, account_id


def mesmas_contas(primeiro: dict) -> dict:
    """Um Pix novo entre as mesmas duas contas do `primeiro`."""
    payload = PayloadGenerator.create_pix_transaction_payload()
    payload["source_account"] = deepcopy(primeiro["source_account"])
    payload["destination_account"] = deepcopy(primeiro["destination_account"])
    return payload


class TestBlockedAccount:
    def test_blocked_account_rejects_without_rules(self):
        """Origem ou destino bloqueado: rejected com ACCOUNT_BLOCKED como motivo
        ÚNICO, porque nenhuma outra regra chega a rodar."""
        for papel in ("source_account", "destination_account"):
            primeiro, _account_id = registra_e_bloqueia(papel)
            payload = mesmas_contas(primeiro)

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 201, f"conta bloqueada em {papel}"
            assert response["status"] == "rejected"
            assert response["metadata"] == {"reasons": ["ACCOUNT_BLOCKED"]}

    def test_rejected_pix_is_recorded(self):
        """Rejeitado também é Pix recebido: fica gravado e o GET devolve a
        mesma análise que o POST."""
        primeiro, _account_id = registra_e_bloqueia("destination_account")
        payload = mesmas_contas(primeiro)

        status, criado = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        status, consultado = RequestGenerator.GET_pix_transaction(payload["id"])
        assert status == 200
        assert consultado == criado

    def test_blocked_only_affects_its_own_account(self):
        """Bloquear o destino não contamina a origem: ela continua pagando
        outros destinos normalmente."""
        primeiro, _account_id = registra_e_bloqueia("destination_account")

        outro_destino = PayloadGenerator.create_pix_transaction_payload()
        outro_destino["source_account"] = deepcopy(primeiro["source_account"])

        status, response = RequestGenerator.POST_pix_transaction(outro_destino)

        assert status == 201
        assert response["status"] == "approved"


class TestUnblockAccount:
    def test_unblock_returns_permitted_account(self):
        _primeiro, account_id = registra_e_bloqueia("source_account")

        status, response = RequestGenerator.POST_unblock_account(account_id)

        assert status == 200
        assert response == {"id": account_id, "status": "PERMITTED"}

    def test_unblock_records_event(self):
        """O desbloqueio grava UM evento PROHIBITED → PERMITTED, sem transação
        de origem (quem desbloqueia é uma pessoa, não um Pix)."""
        _primeiro, account_id = registra_e_bloqueia("source_account")

        status, _response = RequestGenerator.POST_unblock_account(account_id)
        assert status == 200

        eventos = DbUtils.account_events(account_id)
        assert len(eventos) == 1
        assert eventos[0].from_status == "PROHIBITED"
        assert eventos[0].to_status == "PERMITTED"
        assert eventos[0].reason == "MANUAL_UNBLOCK"
        assert eventos[0].transaction_id is None

    def test_unblocked_account_is_approved_again(self):
        primeiro, account_id = registra_e_bloqueia("destination_account")

        status, response = RequestGenerator.POST_pix_transaction(mesmas_contas(primeiro))
        assert response["status"] == "rejected"

        status, _response = RequestGenerator.POST_unblock_account(account_id)
        assert status == 200

        status, response = RequestGenerator.POST_pix_transaction(mesmas_contas(primeiro))
        assert status == 201
        assert response["status"] == "approved"

    def test_second_unblock_is_refused(self):
        """Desbloquear duas vezes: a segunda é 409 e não grava outro evento."""
        _primeiro, account_id = registra_e_bloqueia("source_account")

        status, _response = RequestGenerator.POST_unblock_account(account_id)
        assert status == 200

        status, response = RequestGenerator.POST_unblock_account(account_id)
        assert status == 409
        assert response["code"] == "QIT002007"

        assert len(DbUtils.account_events(account_id)) == 1
