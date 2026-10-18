import time

from tests.utils import DbUtils, PixJourney, RandomGenerator
from tests.utils.pix_journey import DICT_ERROR_DOCUMENT, DICT_MARKED_DOCUMENT, DICT_SLOW_DOCUMENT


def registra_destino(payload: dict) -> int:
    """Manda o primeiro Pix (que registra as contas) e devolve o id do destino."""
    PixJourney.send(payload)
    destination = payload["destination_account"]
    return DbUtils.account_id(destination["branch"], destination["account_number"])


class TestDict:
    def test_marked_destination_is_rejected(self):
        """Destino com marcação de fraude no DICT: rejeita, e nenhuma regra da
        origem roda (o aparelho novo não aparece entre os motivos)."""
        payload = PixJourney.new(destination_document_number=DICT_MARKED_DOCUMENT)

        status, reasons = PixJourney.send(payload)

        assert status == "rejected"
        assert reasons == ["DEST_FRAUD_MARKED"]

    def test_slow_dict_does_not_hold_the_pix(self):
        """O DICT demora mais que o timeout: o motor segue sem ele, e rápido."""
        payload = PixJourney.new(destination_document_number=DICT_SLOW_DOCUMENT)

        started_at = time.perf_counter()
        status, reasons = PixJourney.send(payload)
        elapsed = time.perf_counter() - started_at

        assert "DEST_FRAUD_MARKED" not in reasons
        assert status == "two_factor_required"
        assert elapsed < 1.5, f"o Pix esperou o DICT por {elapsed:.2f} s"

    def test_dict_error_does_not_break_the_pix(self):
        payload = PixJourney.new(destination_document_number=DICT_ERROR_DOCUMENT)

        status, reasons = PixJourney.send(payload)

        assert "DEST_FRAUD_MARKED" not in reasons
        assert status == "two_factor_required"


class TestDestinationCpfVelocity:
    def test_more_than_3_in_the_same_second_is_rejected(self):
        """Rajada: três pagadores no mesmo segundo passam; o quarto é rejeitado."""
        first = PixJourney.new()
        results = [PixJourney.send(first)]
        for _ in range(3):
            results.append(PixJourney.send(PixJourney.to_same_destination(first)))

        for status, reasons in results[:3]:
            assert "DEST_RECEIVING_VELOCITY" not in reasons

        assert results[3] == ("rejected", ["DEST_RECEIVING_VELOCITY"])

    def test_more_than_10_in_a_minute_is_rejected(self):
        """Ritmo abaixo da rajada (no máximo 3 por segundo), mas 11 em menos de
        um minuto: os 10 primeiros passam, o 11º é rejeitado."""
        first = PixJourney.new()
        results = [PixJourney.send(first)]
        for _ in range(10):
            time.sleep(0.35)
            results.append(PixJourney.send(PixJourney.to_same_destination(first)))

        for status, reasons in results[:10]:
            assert "DEST_RECEIVING_VELOCITY" not in reasons

        assert results[10] == ("rejected", ["DEST_RECEIVING_VELOCITY"])

    def test_more_than_100_in_an_hour_is_rejected(self):
        """Laranja paciente: o Pix que registra a conta e mais 98 recebimentos
        há 10 minutos (fora das janelas de 1 s e 1 min). O 100º na mesma hora
        passa; o 101º é rejeitado."""
        first = PixJourney.new()
        destination_id = registra_destino(first)
        DbUtils.seed_received_from_distinct_payers(destination_id, 98, 1000, minutes_ago=10)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))
        assert (status, reasons) == ("rejected", ["DEST_RECEIVING_VELOCITY"])

    def test_counts_every_account_of_the_same_cpf(self):
        """Quatro contas do mesmo CPF, cada uma recebendo um Pix no mesmo
        segundo: a contagem é pelo documento, e o quarto é rejeitado."""
        documento = RandomGenerator.generate_cpf()
        results = [PixJourney.send(PixJourney.new(destination_document_number=documento)) for _ in range(4)]

        for status, reasons in results[:3]:
            assert "DEST_RECEIVING_VELOCITY" not in reasons
        assert results[3] == ("rejected", ["DEST_RECEIVING_VELOCITY"])


class TestDestinationCpfNewAccount:
    """Conta com menos de 5 dias recebendo de muitas contas distintas. O
    histórico de pagadores é plantado 10 minutos atrás, fora das janelas de
    velocidade, pra isolar esta regra."""

    def nova_conta_com_pagadores(self, pagadores_plantados: int) -> dict:
        first = PixJourney.new()
        first["destination_account"]["opening_date"] = PixJourney.days_ago(1)
        destination_id = registra_destino(first)

        DbUtils.seed_received_from_distinct_payers(destination_id, pagadores_plantados, 1000, minutes_ago=10)
        return first

    def test_up_to_20_payers_passes(self):
        # 19 plantados + a origem do primeiro Pix, que paga de novo = 20.
        first = self.nova_conta_com_pagadores(19)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("approved", [])

    def test_more_than_20_payers_requires_2fa(self):
        first = self.nova_conta_com_pagadores(20)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("two_factor_required", ["DEST_NEW_ACCOUNT"])

    def test_more_than_50_payers_is_rejected(self):
        first = self.nova_conta_com_pagadores(50)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("rejected", ["DEST_NEW_ACCOUNT"])

    def test_old_account_with_many_payers_passes(self):
        """A mesma quantidade de pagadores numa conta antiga não é sinal."""
        first = PixJourney.new()
        first["destination_account"]["opening_date"] = PixJourney.days_ago(60)
        destination_id = registra_destino(first)
        DbUtils.seed_received_from_distinct_payers(destination_id, 60, 1000, minutes_ago=10)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("approved", [])


class TestDestinationCnpjAmount:
    """Montante = soma recebida nas últimas 24 h, contando o Pix atual. A
    origem é CNPJ, cujo limite por Pix (R$ 100.000) não interfere."""

    def pix_para_cnpj(self, abertura_dias: int, amount: int) -> dict:
        payload = PixJourney.new(
            amount=amount,
            source_document_number=RandomGenerator.generate_cnpj(),
            destination_document_number=RandomGenerator.generate_cnpj(),
        )
        payload["destination_account"]["opening_date"] = PixJourney.days_ago(abertura_dias)
        return payload

    def test_recent_cnpj_accumulating_more_than_50k_requires_2fa(self):
        """Conta com menos de 30 dias: R$ 40 mil passam; mais R$ 20 mil somam
        R$ 60 mil em 24 h e pedem 2FA."""
        first = self.pix_para_cnpj(abertura_dias=10, amount=4_000_000)
        status, reasons = PixJourney.send(first)
        assert "DEST_HIGH_AMOUNT" not in reasons

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=2_000_000))

        assert (status, reasons) == ("two_factor_required", ["DEST_HIGH_AMOUNT"])

    def test_old_cnpj_without_history_accumulating_more_than_200k_requires_2fa(self):
        """Conta antiga sem histórico: R$ 200 mil exatos passam; o Pix que leva
        a soma acima disso pede 2FA."""
        first = self.pix_para_cnpj(abertura_dias=400, amount=10_000_000)
        PixJourney.send(first)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=10_000_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=1_000))
        assert (status, reasons) == ("two_factor_required", ["DEST_HIGH_AMOUNT"])

    def test_old_cnpj_above_3x_its_daily_average_requires_2fa(self):
        """Com histórico (60 recebimentos de R$ 1.000 há 2 dias): média diária de
        R$ 2.000, limite de R$ 6.000 em 24 h."""
        first = self.pix_para_cnpj(abertura_dias=400, amount=10_000)
        destination_id = registra_destino(first)
        DbUtils.seed_received_from_distinct_payers(destination_id, 60, 100_000, minutes_ago=2 * 24 * 60)

        # R$ 100 + R$ 5.000 = R$ 5.100 em 24 h: abaixo de R$ 6.000.
        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=500_000))
        assert (status, reasons) == ("approved", [])

        # Mais R$ 1.000: R$ 6.100 em 24 h.
        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=100_000))
        assert (status, reasons) == ("two_factor_required", ["DEST_HIGH_AMOUNT"])
