from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import AccountController
from utils.schema_handler import SchemaHandler


class AdminAccountResource:
    @SchemaHandler.validate("post_unblock_account.json")
    def on_post_unblock(self, payload: dict) -> JSONResponse:
        controller = AccountController()
        account = controller.unblock(payload["participant"], payload["branch"], payload["account_number"])
        return JSONResponse(content=jsonable_encoder(account), status_code=http_status.HTTP_200_OK)
