from models import Account


class AccountDTO:
    @staticmethod
    def obj_to_dict(account: Account) -> dict:
        dto = dict()
        dto["participant"] = account.participant
        dto["branch"] = account.branch
        dto["account_number"] = account.account_number
        dto["status"] = account.status
        return dto
