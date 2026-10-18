from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from tests.utils.payload_generator import PayloadGenerator
from tests.utils.request_generator import BANK_ISPB, RequestGenerator


DICT_MARKED_DOCUMENT = "111.444.777-35"
DICT_SLOW_DOCUMENT = "222.555.888-46"
DICT_ERROR_DOCUMENT = "333.666.999-57"

SAO_PAULO = {"latitude": -23.56, "longitude": -46.65}
SAO_PAULO_10KM = {"latitude": -23.47, "longitude": -46.65}
RECIFE = {"latitude": -8.05, "longitude": -34.88}


class PixJourney:
    @staticmethod
    def new(**kwargs) -> dict:
        return PayloadGenerator.create_pix_transaction_payload(**kwargs)

    @staticmethod
    def from_same_source(previous: dict, **kwargs) -> dict:
        payload = PayloadGenerator.create_pix_transaction_payload(**kwargs)
        payload["source_account"] = deepcopy(previous["source_account"])
        payload["source"]["device_id"] = previous["source"]["device_id"]
        return payload

    @staticmethod
    def to_same_destination(previous: dict, **kwargs) -> dict:
        payload = PayloadGenerator.create_pix_transaction_payload(**kwargs)
        payload["destination_account"] = deepcopy(previous["destination_account"])
        return payload

    @staticmethod
    def between_same_accounts(previous: dict, **kwargs) -> dict:
        payload = PixJourney.from_same_source(previous, **kwargs)
        payload["destination_account"] = deepcopy(previous["destination_account"])
        return payload

    @staticmethod
    def send(payload: dict) -> Tuple[str, List[str]]:
        status_code, response = RequestGenerator.POST_pix_transaction(payload)
        assert status_code == 201, f"esperava 201, veio {status_code}: {response}"
        return response["status"], response["metadata"].get("reasons", [])

    @staticmethod
    def days_ago(days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")

    @staticmethod
    def send_until_blocked(next_pix, limit: int = 40) -> list:
        results = []
        for _ in range(limit):
            payload = next_pix()
            status, reasons = PixJourney.send(payload)
            results.append((payload, status, reasons))
            if reasons == ["ACCOUNT_BLOCKED"]:
                return results
        raise AssertionError(f"a conta não foi bloqueada em {limit} Pix")

    @staticmethod
    def block_source(first: dict) -> list:
        return PixJourney.send_until_blocked(lambda: PixJourney.from_same_source(first))

    @staticmethod
    def block_destination(first: dict) -> list:
        return PixJourney.send_until_blocked(lambda: PixJourney.to_same_destination(first))

    @staticmethod
    def unblock_source(payload: dict) -> tuple:
        account = payload["source_account"]
        return RequestGenerator.POST_unblock_account(BANK_ISPB, account["branch"], account["account_number"])

    @staticmethod
    def unblock_destination(payload: dict) -> tuple:
        account = payload["destination_account"]
        return RequestGenerator.POST_unblock_account(
            account["participant"], account["branch"], account["account_number"]
        )
