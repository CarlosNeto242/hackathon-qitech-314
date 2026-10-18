from models import PixTransaction


class PixTransactionDTO:
    """Traduz um Pix gravado na resposta do contrato: `key`, `status`, `metadata`.

    O POST e o GET passam os dois por aqui, e é isso que garante que a
    análise devolvida na hora e a consultada depois nunca divergem.
    """

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
