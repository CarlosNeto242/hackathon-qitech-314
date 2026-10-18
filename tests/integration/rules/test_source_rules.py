from tests.utils import DbUtils, PixJourney, RandomGenerator
from tests.utils.pix_journey import RECIFE, SAO_PAULO, SAO_PAULO_10KM


def register_source(**kwargs) -> dict:
    first = PixJourney.new(**kwargs)
    status, reasons = PixJourney.send(first)
    assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])
    return first


class TestNewDevice:
    def test_unknown_device_on_known_account_requires_2fa(self):
        first = register_source()

        other_device = PixJourney.from_same_source(first)
        other_device["source"]["device_id"] = "dvc-outro"
        status, reasons = PixJourney.send(other_device)
        assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])

        status, reasons = PixJourney.send(PixJourney.from_same_source(first))
        assert (status, reasons) == ("approved", [])

    def test_device_of_rejected_pix_is_not_recognized(self):
        first = register_source()

        fraudster = PixJourney.from_same_source(first)
        fraudster["source"]["device_id"] = "dvc-fraudador"
        fraudster["source"]["geolocation"] = RECIFE
        status, _reasons = PixJourney.send(fraudster)
        assert status == "rejected"

        again = PixJourney.from_same_source(fraudster)
        again["source"]["geolocation"] = SAO_PAULO
        status, reasons = PixJourney.send(again)
        assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])


class TestAmountWithoutHistory:
    def test_cpf_above_2000_requires_2fa(self):
        first = register_source()

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=200_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=200_001))
        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT"])

    def test_cnpj_above_100000_requires_2fa(self):
        first = register_source(source_document_number=RandomGenerator.generate_cnpj())

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=10_000_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=10_000_001))
        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT"])


class TestAmountWithHistory:
    def test_above_1_5x_the_p95_requires_2fa(self):
        first = register_source()
        source = first["source_account"]
        destination = first["destination_account"]
        DbUtils.seed_sent(
            source,
            destination,
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
        first = PixJourney.new()
        first["source_account"]["opening_date"] = PixJourney.days_ago(20)
        PixJourney.send(first)
        source = first["source_account"]
        destination = first["destination_account"]
        DbUtils.seed_sent(
            source,
            destination,
            count=30,
            amount=300_000,
            days_ago=10,
            device_id=first["source"]["device_id"],
        )

        status, reasons = PixJourney.send(PixJourney.from_same_source(first, amount=250_000))

        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT"])


class TestCpfSendingVelocity:
    def test_more_than_3_in_3_minutes_requires_2fa_and_more_than_10_rejects(self):
        first = register_source()
        results = [PixJourney.send(PixJourney.from_same_source(first)) for _ in range(10)]

        assert results[0] == ("approved", [])
        assert results[1] == ("approved", [])

        for result in results[2:9]:
            assert result == ("two_factor_required", ["SRC_SENDING_VELOCITY"])

        assert results[9] == ("rejected", ["SRC_SENDING_VELOCITY"])


class TestCnpjSendingBurst:
    def test_without_history_more_than_15_in_an_hour_requires_2fa(self):
        first = register_source(source_document_number=RandomGenerator.generate_cnpj())
        results = [PixJourney.send(PixJourney.from_same_source(first)) for _ in range(15)]

        for result in results[:14]:
            assert result == ("approved", [])
        assert results[14] == ("two_factor_required", ["SRC_SENDING_VELOCITY"])


class TestTeleport:
    def pix_from(self, previous: dict, geolocation) -> dict:
        payload = PixJourney.from_same_source(previous)
        payload["source"]["geolocation"] = geolocation
        return payload

    def test_cpf_impossible_travel_is_rejected(self):
        first = register_source()

        status, reasons = PixJourney.send(self.pix_from(first, RECIFE))

        assert (status, reasons) == ("rejected", ["SRC_LOCATION_MISMATCH"])

    def test_rejected_location_is_not_the_next_reference(self):
        first = register_source()
        PixJourney.send(self.pix_from(first, RECIFE))

        status, reasons = PixJourney.send(self.pix_from(first, SAO_PAULO))

        assert (status, reasons) == ("approved", [])

    def test_short_distance_and_missing_location_are_not_teleport(self):
        first = register_source()

        status, reasons = PixJourney.send(self.pix_from(first, SAO_PAULO_10KM))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(self.pix_from(first, None))
        assert (status, reasons) == ("approved", [])

    def test_cnpj_compares_only_the_same_device(self):
        first = register_source(source_document_number=RandomGenerator.generate_cnpj())

        other_operator = self.pix_from(first, RECIFE)
        other_operator["source"]["device_id"] = "dvc-filial-recife"
        status, reasons = PixJourney.send(other_operator)
        assert (status, reasons) == ("two_factor_required", ["SRC_NEW_DEVICE"])

        status, reasons = PixJourney.send(self.pix_from(first, RECIFE))
        assert (status, reasons) == ("rejected", ["SRC_LOCATION_MISMATCH"])


class TestCombination:
    def test_several_2fa_signals_are_still_2fa(self):
        payload = PixJourney.new(amount=300_000)

        status, reasons = PixJourney.send(payload)

        assert (status, reasons) == ("two_factor_required", ["SRC_HIGH_AMOUNT", "SRC_NEW_DEVICE"])

    def test_destination_2fa_does_not_stop_source_rules(self):
        first = register_source(source_document_number=RandomGenerator.generate_cnpj())

        payload = PixJourney.from_same_source(
            first, amount=6_000_000, destination_document_number=RandomGenerator.generate_cnpj()
        )
        payload["destination_account"]["opening_date"] = PixJourney.days_ago(10)
        payload["source"]["geolocation"] = RECIFE

        status, reasons = PixJourney.send(payload)

        assert (status, reasons) == ("rejected", ["SRC_LOCATION_MISMATCH", "DEST_HIGH_AMOUNT"])
