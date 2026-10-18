from uuid import uuid4

from tests.utils.random_generator import RandomGenerator


class PayloadGenerator:
    @staticmethod
    def create_pix_transaction_payload(
        pix_id: str = None,
        amount: int = 15000,
        source_document_number: str = None,
        destination_document_number: str = None,
    ) -> dict:
        """Um Pix valido, com contas novas a cada chamada.

        As contas saem com numero aleatorio porque todos os testes dividem
        o mesmo banco: duas chamadas que caissem na mesma conta com CPFs
        diferentes bateriam na regra de divergencia de dados (422). Quem
        quer a MESMA conta em dois Pix copia o bloco da conta do primeiro.
        """
        if pix_id is None:
            # "pix-" + 12 hexadecimais = 16 caracteres, o limite do id.
            pix_id = f"pix-{uuid4().hex[:12]}"

        if source_document_number is None:
            source_document_number = RandomGenerator.generate_cpf()

        if destination_document_number is None:
            destination_document_number = RandomGenerator.generate_cpf()

        payload = {
            "id": pix_id,
            "amount": amount,
            "transaction_date": "2026-10-17T22:15:00-03:00",
            "source_account": {
                "branch": "0001",
                "account_number": RandomGenerator.generate_account_number(),
                "opening_date": "2025-03-02T10:00:00-03:00",
                "owner": {"document_number": source_document_number},
            },
            "destination_account": {
                "participant": "60701190",
                "branch": "3675",
                "account_number": RandomGenerator.generate_account_number(),
                "opening_date": "2026-10-10T09:00:00-03:00",
                "owner": {"document_number": destination_document_number},
            },
            "source": {
                "device_id": f"dvc-{uuid4().hex[:8]}",
                "channel": "app",
                "ip": "198.51.100.23",
                "geolocation": {"latitude": -23.56, "longitude": -46.65},
            },
        }
        return payload
