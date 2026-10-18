from tests.utils import BANK_ISPB, PixJourney, RequestGenerator


def blocked(role: str) -> dict:
    first = PixJourney.new()
    PixJourney.send(first)
    if role == "source_account":
        PixJourney.block_source(first)
    else:
        PixJourney.block_destination(first)
    return first


class TestBlockedAccount:
    def test_blocked_account_rejects_without_rules(self):
        for role in ("source_account", "destination_account"):
            first = blocked(role)

            status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))

            assert (status, reasons) == ("rejected", ["ACCOUNT_BLOCKED"]), f"conta bloqueada em {role}"

    def test_rejected_pix_is_recorded(self):
        first = blocked("destination_account")
        payload = PixJourney.between_same_accounts(first)

        status, created = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        status, fetched = RequestGenerator.GET_pix_transaction(payload["id"])
        assert status == 200
        assert fetched == created

    def test_blocked_only_affects_its_own_account(self):
        first = blocked("destination_account")

        status, reasons = PixJourney.send(PixJourney.from_same_source(first))

        assert (status, reasons) == ("approved", [])


class TestUnblockAccount:
    def test_unblock_returns_permitted_account(self):
        first = blocked("source_account")

        status, response = PixJourney.unblock_source(first)

        assert status == 200
        assert response == {
            "participant": BANK_ISPB,
            "branch": first["source_account"]["branch"],
            "account_number": first["source_account"]["account_number"],
            "status": "PERMITTED",
        }

    def test_unblocked_account_is_analyzed_again(self):
        first = blocked("destination_account")

        status, _response = PixJourney.unblock_destination(first)
        assert status == 200

        _status, reasons = PixJourney.send(PixJourney.between_same_accounts(first))
        assert reasons != ["ACCOUNT_BLOCKED"]

    def test_second_unblock_is_refused(self):
        first = blocked("source_account")

        status, _response = PixJourney.unblock_source(first)
        assert status == 200

        status, response = PixJourney.unblock_source(first)
        assert status == 409
        assert response["code"] == "QIT001013"
