from concurrent.futures import ThreadPoolExecutor

from tests.utils import PayloadGenerator, RequestGenerator


class TestPixTransactionIdempotency:
    def test_same_pix_twice_returns_recorded_analysis(self):
        payload = PayloadGenerator.create_pix_transaction_payload()

        status, primeira = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        status, segunda = RequestGenerator.POST_pix_transaction(payload)
        assert status == 200
        assert segunda == primeira

    def test_same_pix_id_with_other_content_is_a_conflict(self):
        """O mesmo pix_id com outro conteúdo é 409: devolver a análise antiga
        seria aprovar uma transação que nunca foi analisada. O Pix original
        continua gravado e consultável, intacto."""
        payload = PayloadGenerator.create_pix_transaction_payload()
        status, primeira = RequestGenerator.POST_pix_transaction(payload)
        assert status == 201

        outro = PayloadGenerator.create_pix_transaction_payload(pix_id=payload["id"], amount=999)
        status, response = RequestGenerator.POST_pix_transaction(outro)

        assert status == 409
        assert response["code"] == "QIT002008"

        status, consultado = RequestGenerator.GET_pix_transaction(payload["id"])
        assert status == 200
        assert consultado == primeira

    def test_concurrent_requests_with_same_pix_id(self):
        """Dez requisições iguais ao mesmo tempo: uma analisa (201), as outras
        recebem a mesma análise (200). Nenhum 500, uma chave só."""
        payload = PayloadGenerator.create_pix_transaction_payload()

        with ThreadPoolExecutor(max_workers=10) as executor:
            resultados = list(executor.map(lambda _: RequestGenerator.POST_pix_transaction(payload), range(10)))

        status_codes = sorted(status for status, _response in resultados)
        chaves = {response["key"] for _status, response in resultados}

        assert status_codes == [200] * 9 + [201]
        assert len(chaves) == 1
