from fastapi import status as http_status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from controllers import AccountController


class AdminAccountResource:

    def on_post_unblock(self, account_id: int) -> JSONResponse:
        controller = AccountController()
        account = controller.unblock(account_id)
        return JSONResponse(content=jsonable_encoder(account), status_code=http_status.HTTP_200_OK)
