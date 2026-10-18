import time

from tests.utils import DbUtils, PixJourney, RandomGenerator
from tests.utils.pix_journey import DICT_ERROR_DOCUMENT, DICT_MARKED_DOCUMENT, DICT_SLOW_DOCUMENT


def register_destination(payload: dict) -> dict:
    PixJourney.send(payload)
    return payload["destination_account"]


class TestDict:
    def test_marked_destination_is_rejected(self):
        payload = PixJourney.new(destination_document_number=DICT_MARKED_DOCUMENT)

        status, reasons = PixJourney.send(payload)

        assert status == "rejected"
        assert reasons == ["DEST_FRAUD_MARKED"]

    def test_slow_dict_does_not_hold_the_pix(self):
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
        first = PixJourney.new()
        results = [PixJourney.send(first)]
        for _ in range(3):
            results.append(PixJourney.send(PixJourney.to_same_destination(first)))

        for status, reasons in results[:3]:
            assert "DEST_RECEIVING_VELOCITY" not in reasons

        assert results[3] == ("rejected", ["DEST_RECEIVING_VELOCITY"])

    def test_more_than_10_in_a_minute_is_rejected(self):
        first = PixJourney.new()
        results = [PixJourney.send(first)]
        for _ in range(10):
            time.sleep(0.35)
            results.append(PixJourney.send(PixJourney.to_same_destination(first)))

        for status, reasons in results[:10]:
            assert "DEST_RECEIVING_VELOCITY" not in reasons

        assert results[10] == ("rejected", ["DEST_RECEIVING_VELOCITY"])

    def test_more_than_100_in_an_hour_is_rejected(self):
        first = PixJourney.new()
        destination = register_destination(first)
        DbUtils.seed_received_from_distinct_payers(destination, 98, 1000, minutes_ago=10)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))
        assert (status, reasons) == ("rejected", ["DEST_RECEIVING_VELOCITY"])

    def test_counts_every_account_of_the_same_cpf(self):
        document = RandomGenerator.generate_cpf()
        results = [PixJourney.send(PixJourney.new(destination_document_number=document)) for _ in range(4)]

        for status, reasons in results[:3]:
            assert "DEST_RECEIVING_VELOCITY" not in reasons
        assert results[3] == ("rejected", ["DEST_RECEIVING_VELOCITY"])


class TestDestinationCpfNewAccount:
    def new_account_with_payers(self, seeded_payers: int) -> dict:
        first = PixJourney.new()
        first["destination_account"]["opening_date"] = PixJourney.days_ago(1)
        destination = register_destination(first)

        DbUtils.seed_received_from_distinct_payers(destination, seeded_payers, 1000, minutes_ago=10)
        return first

    def test_up_to_20_payers_passes(self):
        first = self.new_account_with_payers(19)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("approved", [])

    def test_more_than_20_payers_requires_2fa(self):
        first = self.new_account_with_payers(20)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("two_factor_required", ["DEST_NEW_ACCOUNT"])

    def test_more_than_50_payers_is_rejected(self):
        first = self.new_account_with_payers(50)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("rejected", ["DEST_NEW_ACCOUNT"])

    def test_old_account_with_many_payers_passes(self):
        first = PixJourney.new()
        first["destination_account"]["opening_date"] = PixJourney.days_ago(60)
        destination = register_destination(first)
        DbUtils.seed_received_from_distinct_payers(destination, 60, 1000, minutes_ago=10)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

        assert (status, reasons) == ("approved", [])


class TestDestinationCnpjAmount:
    def pix_to_cnpj(self, opening_days: int, amount: int) -> dict:
        payload = PixJourney.new(
            amount=amount,
            source_document_number=RandomGenerator.generate_cnpj(),
            destination_document_number=RandomGenerator.generate_cnpj(),
        )
        payload["destination_account"]["opening_date"] = PixJourney.days_ago(opening_days)
        return payload

    def test_recent_cnpj_accumulating_more_than_50k_requires_2fa(self):
        first = self.pix_to_cnpj(opening_days=10, amount=4_000_000)
        status, reasons = PixJourney.send(first)
        assert "DEST_HIGH_AMOUNT" not in reasons

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=2_000_000))

        assert (status, reasons) == ("two_factor_required", ["DEST_HIGH_AMOUNT"])

    def test_old_cnpj_without_history_accumulating_more_than_200k_requires_2fa(self):
        first = self.pix_to_cnpj(opening_days=400, amount=10_000_000)
        PixJourney.send(first)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=10_000_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=1_000))
        assert (status, reasons) == ("two_factor_required", ["DEST_HIGH_AMOUNT"])

    def test_old_cnpj_above_3x_its_daily_average_requires_2fa(self):
        first = self.pix_to_cnpj(opening_days=400, amount=10_000)
        destination = register_destination(first)
        DbUtils.seed_received_from_distinct_payers(destination, 60, 100_000, minutes_ago=2 * 24 * 60)

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=500_000))
        assert (status, reasons) == ("approved", [])

        status, reasons = PixJourney.send(PixJourney.between_same_accounts(first, amount=100_000))
        assert (status, reasons) == ("two_factor_required", ["DEST_HIGH_AMOUNT"])
