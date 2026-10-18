from models import Account


class AccountDTO:
    @staticmethod
    def obj_to_dict(account: Account) -> dict:
        dto = dict()
        dto["id"] = account.id
        dto["status"] = account.status
        return dto
