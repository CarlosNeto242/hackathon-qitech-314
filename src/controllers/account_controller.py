from controllers.base_controller import BaseController
from dtos import AccountDTO
from errors import AccountAlreadyPermitted, NotFoundAccount
from models import Account, AccountEvent
from repositories import AccountRepository


class AccountController(BaseController):

    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)

    def unblock(self, account_id: int) -> dict:
        account = self.account_repository.get_by_id_for_update(account_id)
        if account is None:
            raise NotFoundAccount(account_id)

        if account.status == Account.PERMITTED:
            raise AccountAlreadyPermitted(account_id)

        self.account_repository.update_status(account, Account.PERMITTED, AccountEvent.MANUAL_UNBLOCK)

        account_dto = AccountDTO.obj_to_dict(account)
        self.session.commit()

        return account_dto
