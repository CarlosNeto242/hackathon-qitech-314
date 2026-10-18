from os import environ

from tests.utils.requisition import ClientRequisition, BaseConnectorResponse


INTERNAL_TOKEN = environ.get("INTERNAL_TOKEN", "default_token")
BANK_ISPB = environ.get("BANK_ISPB", "32402502")


class RequestGenerator:
    @staticmethod
    def POST_pix_transaction(pix_transaction_payload: dict) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "POST",
            "/pix/transaction",
            payload=pix_transaction_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        return response.response_status, response.response_json

    @staticmethod
    def GET_pix_transaction(pix_id: str) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "GET",
            f"/pix/transaction/{pix_id}",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        return response.response_status, response.response_json

    @staticmethod
    def POST_unblock_account(participant: str, branch: str, account_number: str) -> BaseConnectorResponse:
        response = ClientRequisition.send(
            "POST",
            "/admin/accounts/unblock",
            payload={"participant": participant, "branch": branch, "account_number": account_number},
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        return response.response_status, response.response_json
