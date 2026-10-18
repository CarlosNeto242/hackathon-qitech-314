from tests.utils import PayloadGenerator, RequestGenerator


class TestPixTransactionGet:
    def test_get_returns_same_body_as_post(self):
        payload = PayloadGenerator.create_pix_transaction_payload()

        status, created = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        status, fetched = RequestGenerator.GET_pix_transaction(payload["id"])
        assert status == 200
        assert fetched == created

    def test_not_found(self):
        status, response = RequestGenerator.GET_pix_transaction("pix-que-nunca-existiu")

        assert status == 404
        assert response["code"] == "QIT002001"
