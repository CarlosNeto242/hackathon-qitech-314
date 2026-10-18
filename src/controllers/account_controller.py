from controllers.base_controller import BaseController
from dtos import AccountDTO
from errors import AccountAlreadyPermitted, NotFoundAccount
from models import Account, AccountEvent
from repositories import AccountRepository


class AccountController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)

    def unblock(self, participant: str, branch: str, account_number: str) -> dict:
        account = self.account_repository.get_by_identity_for_update(participant, branch, account_number)
        if account is None:
            raise NotFoundAccount(participant, branch, account_number)

        if account.status == Account.PERMITTED:
            raise AccountAlreadyPermitted(participant, branch, account_number)

        self.account_repository.update_status(account, Account.PERMITTED, AccountEvent.MANUAL_UNBLOCK)

        account_dto = AccountDTO.obj_to_dict(account)
        self.session.commit()

        return account_dto
