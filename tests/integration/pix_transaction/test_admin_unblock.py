from tests.utils import BANK_ISPB, PixJourney, RandomGenerator, RequestGenerator
from tests.utils.requisition import ClientRequisition


class TestAdminUnblock:
    def test_requires_internal_token(self):
        response = ClientRequisition.send(
            "POST",
            "/admin/accounts/unblock",
            payload={"participant": BANK_ISPB, "branch": "0001", "account_number": "1"},
        )

        assert response.response_status == 403
        assert response.response_json["code"] == "QIT000002"

    def test_not_found(self):
        status, response = RequestGenerator.POST_unblock_account(
            BANK_ISPB, "0001", RandomGenerator.generate_account_number()
        )

        assert status == 404
        assert response["code"] == "QIT002006"

    def test_refuses_invalid_payload(self):
        for participant, branch, account_number in (("123", "0001", "1"), (BANK_ISPB, "ag-01", "1")):
            status, response = RequestGenerator.POST_unblock_account(participant, branch, account_number)

            assert status == 400
            assert response["code"] == "QIT000001"

    def test_refuses_account_that_is_not_blocked(self):
        payload = PixJourney.new()
        PixJourney.send(payload)

        status, response = PixJourney.unblock_source(payload)

        assert status == 409
        assert response["code"] == "QIT002007"
