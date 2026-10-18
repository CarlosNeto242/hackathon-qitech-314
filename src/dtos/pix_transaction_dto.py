from models import PixTransaction


class PixTransactionDTO:
    @staticmethod
    def obj_to_dict(pix_transaction: PixTransaction) -> dict:
        metadata = {}
        if pix_transaction.decision_reasons:
            metadata["reasons"] = list(pix_transaction.decision_reasons)

        dto = dict()
        dto["key"] = str(pix_transaction.transaction_key)
        dto["status"] = pix_transaction.status
        dto["metadata"] = metadata
        return dto
