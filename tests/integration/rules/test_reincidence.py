from tests.utils import DbUtils, PixJourney, RequestGenerator


def ate_bloquear(next_pix, limite: int = 40) -> list:
    """Manda Pix até aparecer o primeiro ACCOUNT_BLOCKED (inclusive).

    Conta o comportamento, não o relógio: quantos Pix cada janela de
    velocidade deixa passar depende de quão rápido a máquina manda, mas o
    número de rejeições POR RISCO até o bloqueio não depende.
    """
    results = []
    for _ in range(limite):
        payload = next_pix()
        status, reasons = PixJourney.send(payload)
        results.append((payload, status, reasons))
        if reasons == ["ACCOUNT_BLOCKED"]:
            return results
    raise AssertionError(f"a conta não foi bloqueada em {limite} Pix")


def rejeicoes_por_risco(results: list) -> list:
    return [result for result in results if result[1] == "rejected" and result[2] != ["ACCOUNT_BLOCKED"]]


class TestDestinationReincidence:
    def test_destination_is_blocked_after_more_than_8_risk_rejections(self):
        """Conta de passagem: muitos pagadores em rajada. A 9ª rejeição por
        risco bloqueia o destino, com o evento apontando o Pix que disparou; o
        Pix seguinte já é rejeitado como conta bloqueada."""
        first = PixJourney.new()
        PixJourney.send(first)

        results = ate_bloquear(lambda: PixJourney.to_same_destination(first))
        rejeicoes = rejeicoes_por_risco(results)

        assert len(rejeicoes) == 9
        assert all(reasons == ["DEST_RECEIVING_VELOCITY"] for _payload, _status, reasons in rejeicoes)

        destination = first["destination_account"]
        destination_id = DbUtils.account_id(destination["branch"], destination["account_number"])
        eventos = DbUtils.account_events(destination_id)
        gatilho = rejeicoes[-1][0]

        assert len(eventos) == 1
        assert (eventos[0].from_status, eventos[0].to_status) == ("PERMITTED", "PROHIBITED")
        assert eventos[0].reason == "REPEATED_RISK_REJECTIONS_DEST"
        assert eventos[0].transaction_id == DbUtils.transaction_id(gatilho["id"])

    def test_counting_restarts_after_unblock(self):
        """Depois do desbloqueio, as rejeições antigas (e os ACCOUNT_BLOCKED) não
        contam: uma nova rejeição por risco não bloqueia de novo."""
        first = PixJourney.new()
        PixJourney.send(first)
        ate_bloquear(lambda: PixJourney.to_same_destination(first))

        destination = first["destination_account"]
        destination_id = DbUtils.account_id(destination["branch"], destination["account_number"])
        status_code, _response = RequestGenerator.POST_unblock_account(destination_id)
        assert status_code == 200

        # Ainda dentro da janela de 1 minuto: rejeita por velocidade, mas é a
        # primeira rejeição desde o desbloqueio.
        status, reasons = PixJourney.send(PixJourney.to_same_destination(first))
        assert (status, reasons) == ("rejected", ["DEST_RECEIVING_VELOCITY"])

        assert [evento.reason for evento in DbUtils.account_events(destination_id)] == [
            "REPEATED_RISK_REJECTIONS_DEST",
            "MANUAL_UNBLOCK",
        ]


class TestSourceReincidence:
    def test_source_is_blocked_after_more_than_10_risk_rejections(self):
        """O cliente disparando Pix sem parar (script, conta invadida): a 11ª
        rejeição por risco bloqueia a origem, que exige mais evidência que o
        destino."""
        first = PixJourney.new()
        PixJourney.send(first)

        results = ate_bloquear(lambda: PixJourney.from_same_source(first))
        rejeicoes = rejeicoes_por_risco(results)

        assert len(rejeicoes) == 11
        assert all(reasons == ["SRC_SENDING_VELOCITY"] for _payload, _status, reasons in rejeicoes)

        source = first["source_account"]
        source_id = DbUtils.account_id(source["branch"], source["account_number"])
        eventos = DbUtils.account_events(source_id)

        assert len(eventos) == 1
        assert eventos[0].reason == "REPEATED_RISK_REJECTIONS_SRC"
        assert eventos[0].transaction_id == DbUtils.transaction_id(rejeicoes[-1][0]["id"])
