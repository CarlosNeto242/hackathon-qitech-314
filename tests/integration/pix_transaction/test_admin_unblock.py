from tests.utils import DbUtils, PayloadGenerator, RequestGenerator
from tests.utils.requisition import ClientRequisition


class TestAdminUnblock:
    def test_requires_internal_token(self):
        response = ClientRequisition.send("POST", "/admin/accounts/1/unblock")

        assert response.response_status == 403
        assert response.response_json["code"] == "QIT000002"

    def test_not_found(self):
        status, response = RequestGenerator.POST_unblock_account(999999999)

        assert status == 404
        assert response["code"] == "QIT002006"

    def test_refuses_non_numeric_id(self):
        status, response = RequestGenerator.POST_unblock_account("abc")

        assert status == 400
        assert response["code"] == "QIT000010"

    def test_refuses_account_that_is_not_blocked(self):
        """A API não devolve o id das contas, então o teste parte de um banco
        zerado: o primeiro Pix registra a origem primeiro, e ela nasce com id 1."""
        DbUtils.rollback()

        payload = PayloadGenerator.create_pix_transaction_payload()
        status, _response = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        status, response = RequestGenerator.POST_unblock_account(1)

        assert status == 409
        assert response["code"] == "QIT002007"
