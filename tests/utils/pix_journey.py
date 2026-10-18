from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from tests.utils.payload_generator import PayloadGenerator
from tests.utils.request_generator import RequestGenerator

# Documentos com comportamento fixo no mock do DICT (mocks/dict/server.py).
DICT_MARKED_DOCUMENT = "111.444.777-35"
DICT_SLOW_DOCUMENT = "222.555.888-46"
DICT_ERROR_DOCUMENT = "333.666.999-57"

SAO_PAULO = {"latitude": -23.56, "longitude": -46.65}
SAO_PAULO_10KM = {"latitude": -23.47, "longitude": -46.65}
RECIFE = {"latitude": -8.05, "longitude": -34.88}


class PixJourney:
    """Atalhos pra montar jornadas de vários Pix entre as mesmas contas.

    Cada teste de regra é uma sequência de Pix pela API, como um cliente de
    verdade faria. Estes atalhos só montam os payloads: quem decide é sempre
    o motor, do outro lado do HTTP.
    """

    @staticmethod
    def new(**kwargs) -> dict:
        """Um Pix entre duas contas novas, de um aparelho novo."""
        return PayloadGenerator.create_pix_transaction_payload(**kwargs)

    @staticmethod
    def from_same_source(previous: dict, **kwargs) -> dict:
        """Um Pix novo da mesma conta de origem, pelo mesmo aparelho, para um
        destino novo."""
        payload = PayloadGenerator.create_pix_transaction_payload(**kwargs)
        payload["source_account"] = deepcopy(previous["source_account"])
        payload["source"]["device_id"] = previous["source"]["device_id"]
        return payload

    @staticmethod
    def to_same_destination(previous: dict, **kwargs) -> dict:
        """Um Pix novo para o mesmo destino, de uma origem nova."""
        payload = PayloadGenerator.create_pix_transaction_payload(**kwargs)
        payload["destination_account"] = deepcopy(previous["destination_account"])
        return payload

    @staticmethod
    def between_same_accounts(previous: dict, **kwargs) -> dict:
        """Um Pix novo entre as mesmas duas contas, pelo mesmo aparelho."""
        payload = PixJourney.from_same_source(previous, **kwargs)
        payload["destination_account"] = deepcopy(previous["destination_account"])
        return payload

    @staticmethod
    def send(payload: dict) -> Tuple[str, List[str]]:
        """Manda o Pix e devolve (status, motivos). Todo Pix válido é analisado
        e gravado: a resposta é sempre 201, qualquer que seja a decisão."""
        status_code, response = RequestGenerator.POST_pix_transaction(payload)
        assert status_code == 201, f"esperava 201, veio {status_code}: {response}"
        return response["status"], response["metadata"].get("reasons", [])

    @staticmethod
    def days_ago(days: int) -> str:
        """Uma data `days` dias atrás, no formato do payload."""
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
