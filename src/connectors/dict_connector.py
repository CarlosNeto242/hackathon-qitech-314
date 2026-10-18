import requests

from connectors.rest_connector import BaseConnectorResponse, RestConnector
from constants import BANK_ISPB, DICT_API_INTERNAL_TOKEN, DICT_API_TIMEOUT, DICT_API_URL


class DictUnavailable(Exception):
    pass


class DictConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=__name__,
            base_url=DICT_API_URL,
            timeout=DICT_API_TIMEOUT,
            internal_token=DICT_API_INTERNAL_TOKEN,
        )

    def get_person_statistics(self, document_number: str) -> BaseConnectorResponse:
        try:
            return self.send(
                endpoint=f"/dict/{document_number}/statistics",
                method="GET",
                headers={"PI-RequestingParticipant": BANK_ISPB},
            )
        except requests.exceptions.RequestException as error:
            self.logger.warning(f"DICT indisponivel: {type(error).__name__}: {error}")
            raise DictUnavailable() from error
