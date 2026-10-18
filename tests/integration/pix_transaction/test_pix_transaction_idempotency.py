from concurrent.futures import ThreadPoolExecutor

from tests.utils import PayloadGenerator, RequestGenerator


class TestPixTransactionIdempotency:
    def test_same_pix_twice_returns_recorded_analysis(self):
        payload = PayloadGenerator.create_pix_transaction_payload()

        status, first_response = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        status, second_response = RequestGenerator.POST_pix_transaction(payload)
        assert status == 200
        assert second_response == first_response

    def test_same_pix_id_with_other_content_is_a_conflict(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        status, first_response = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        other = PayloadGenerator.create_pix_transaction_payload(pix_id=payload["id"], amount=999)
        status, response = RequestGenerator.POST_pix_transaction(other)

        assert status == 409
        assert response["code"] == "QIT002008"

        status, fetched = RequestGenerator.GET_pix_transaction(payload["id"])
        assert status == 200
        assert fetched == first_response

    def test_concurrent_requests_with_same_pix_id(self):
        payload = PayloadGenerator.create_pix_transaction_payload()

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda _: RequestGenerator.POST_pix_transaction(payload), range(10)))

        status_codes = sorted(status for status, _response in results)
        keys = {response["key"] for _status, response in results}

        assert status_codes == [200] * 9 + [201]
        assert len(keys) == 1
