from tests.utils import DbUtils, PixJourney, RandomGenerator
from tests.utils.pix_journey import RECIFE, SAO_PAULO, SAO_PAULO_10KM


def registra_origem(**kwargs) -> dict:
    """Primeiro Pix da conta: registra as contas e o aparelho (pede 2FA)."""
    first = PixJourney.new(**kwargs)
    status, reasons = PixJourney.send(first)
    assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])
    return first


class TestNewDevice:
    def test_unknown_device_on_known_account_requires_2fa(self):
        first = registra_origem()

        outro_aparelho = PixJourney.from_same_source(first)
        outro_aparelho["source"]["device_id"] = "dvc-outro"
        status, reasons = PixJourney.send(outro_aparelho)
        assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])

        status, reasons = PixJourney.send(PixJourney.from_same_source(first))
        assert (status, reasons) == ("approved", [])

    def test_device_of_rejected_pix_is_not_recognized(self):
        """Pix rejeitado não reconhece o aparelho: o fraudador barrado não
        "ensina" o aparelho dele à conta."""
        first = registra_origem()

        fraudador = PixJourney.from_same_source(first)
        fraudador["source"]["device_id"] = "dvc-fraudador"
        fraudador["source"]["geolocation"] = RECIFE
        status, _reasons = PixJourney.send(fraudador)
        assert status == "rejected"

        de_novo = PixJourney.from_same_source(fraudador)
        de_novo["source"]["geolocation"] = SAO_PAULO
        status, reasons = PixJourney.send(de_novo)
        assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])


class TestAmountWithoutHistory:
    def test_cpf_above_2000_requires_2fa(self):
        first = registra_origem()

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=200_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=200_001))
        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT"])

    def test_cnpj_above_100000_requires_2fa(self):
        first = registra_origem(source_document_number=RandomGenerator.generate_cnpj())

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=10_000_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=10_000_001))
        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT"])


class TestAmountWithHistory:
    def test_above_1_5x_the_p95_requires_2fa(self):
        """Conta antiga com 30 Pix de R$ 3.000 há 10 dias: p95 de R$ 3.000,
        limite de R$ 4.500. O histórico é plantado no banco; os Pix decididos
        passam pela API."""
        first = registra_origem()
        source = first["source_account"]
        destination = first["destination_account"]
        DbUtils.seed_sent(
            DbUtils.account_id(source["branch"], source["account_number"]),
            DbUtils.account_id(destination["branch"], destination["account_number"]),
            count=30,
            amount=300_000,
            days_ago=10,
            device_id=first["source"]["device_id"],
        )

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=450_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=450_001))
        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT"])

    def test_new_account_never_has_history(self):
        """Mesmo com 30 Pix no histórico, conta com menos de 60 dias não tem
        histórico: acima do limite, pede 2FA."""
        first = PixJourney.new()
        first["source_account"]["opening_date"] = PixJourney.days_ago(20)
        PixJourney.send(first)
        source = first["source_account"]
        destination = first["destination_account"]
        DbUtils.seed_sent(
            DbUtils.account_id(source["branch"], source["account_number"]),
            DbUtils.account_id(destination["branch"], destination["account_number"]),
            count=30,
            amount=300_000,
            days_ago=10,
            device_id=first["source"]["device_id"],
        )

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=250_000))

        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT"])


class TestCpfSendingVelocity:
    def test_more_than_3_in_3_minutes_requires_2fa_and_more_than_10_rejects(self):
        """O mesmo cliente, pelo mesmo aparelho, para destinos diferentes."""
        first = registra_origem()
        results = [PixJourney.send(PixJourney.from_same_source(first)) for _ in range(10)]

        # 2º e 3º Pix: normais.
        assert results[0] == ("approved", [])
        assert results[1] == ("approved", [])
        # 4º ao 10º: 2FA.
        for result in results[2:9]:
            assert result == ("two_factor_required", ["SRC_SENDING_VELOCITY"])
        # 11º: rejeitado.
        assert results[9] == ("rejected", ["SRC_SENDING_VELOCITY"])


class TestCnpjSendingBurst:
    def test_without_history_more_than_15_in_an_hour_requires_2fa(self):
        first = registra_origem(source_document_number=RandomGenerator.generate_cnpj())
        results = [PixJourney.send(PixJourney.from_same_source(first)) for _ in range(15)]

        for result in results[:14]:
            assert result == ("approved", [])
        assert results[14] == ("two_factor_required", ["SRC_SENDING_VELOCITY"])


class TestTeleport:
    def pix_de(self, previous: dict, geolocation) -> dict:
        payload = PixJourney.from_same_source(previous)
        payload["source"]["geolocation"] = geolocation
        return payload

    def test_cpf_impossible_travel_is_rejected(self):
        """São Paulo e, segundos depois, Recife: ninguém viaja a 2.000 km/s."""
        first = registra_origem()

        status, reasons = PixJourney.send(self.pix_de(first, RECIFE))

        assert (status, reasons) == ("rejected", ["SRC_LOCATION_MISMATCH"])

    def test_rejected_location_is_not_the_next_reference(self):
        """Depois do Pix barrado em Recife, o cliente volta a pagar de São Paulo:
        a comparação é com o último Pix ACEITO (São Paulo), não com Recife."""
        first = registra_origem()
        PixJourney.send(self.pix_de(first, RECIFE))

        status, reasons = PixJourney.send(self.pix_de(first, SAO_PAULO))

        assert (status, reasons) == ("approved", [])

    def test_short_distance_and_missing_location_are_not_teleport(self):
        first = registra_origem()

        status, reasons = PixJourney.send(self.pix_de(first, SAO_PAULO_10KM))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(self.pix_de(first, None))
        assert (status, reasons) == ("approved", [])

    def test_cnpj_compares_only_the_same_device(self):
        """Empresa tem operadores em lugares diferentes: outro aparelho em Recife
        é só aparelho novo; o MESMO aparelho em Recife é teleporte."""
        first = registra_origem(source_document_number=RandomGenerator.generate_cnpj())

        outro_operador = self.pix_de(first, RECIFE)
        outro_operador["source"]["device_id"] = "dvc-filial-recife"
        status, reasons = PixJourney.send(outro_operador)
        assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])

        status, reasons = PixJourney.send(self.pix_de(first, RECIFE))
        assert (status, reasons) == ("rejected", ["SRC_LOCATION_MISMATCH"])


class TestCombination:
    def test_several_2fa_signals_are_still_2fa(self):
        """Sinais não se somam: aparelho novo e valor alto continuam 2FA."""
        payload = PixJourney.new(amount=300_000)

        status, reasons = PixJourney.send(payload)

        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT", "SRC_NEW_DEVICE"])

    def test_destination_2fa_does_not_stop_source_rules(self):
        """2FA no destino segue pra origem; a rejeição da origem prevalece, e os
        motivos de rejeição vêm antes dos de 2FA."""
        first = registra_origem(source_document_number=RandomGenerator.generate_cnpj())

        payload = PixJourney.from_same_source(
            first, amount=6_000_000, destination_document_number=RandomGenerator.generate_cnpj()
        )
        payload["destination_account"]["opening_date"] = PixJourney.days_ago(10)
        payload["source"]["geolocation"] = RECIFE

        status, reasons = PixJourney.send(payload)

        assert (status, reasons) == ("rejected", ["SRC_LOCATION_MISMATCH", "DEST_HIGH_AMOUNT"])
