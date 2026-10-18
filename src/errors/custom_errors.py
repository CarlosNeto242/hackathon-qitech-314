from errors import QIException


# ─────────────────────────────────────────────────────────────────────
# Antifraude Pix (QIT002xxx)
# ─────────────────────────────────────────────────────────────────────


class NotFoundPixTransaction(QIException):
    code = "QIT002001"

    def __init__(self, pix_id) -> None:
        title = "Pix Transaction not Found"
        http_status = 404
        description = f"Pix transaction with id {pix_id} was not found."
        translation = f"O Pix com id {pix_id} não foi encontrado."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidPixDocumentNumber(QIException):
    """CPF ou CNPJ com o formato certo e os dígitos verificadores errados.

    Mesma lógica do InvalidDocumentNumber: 422, não 400. Diz o CAMPO, e
    não o número, porque o número é dado pessoal e não volta na resposta.
    """

    code = "QIT002002"

    def __init__(self, field) -> None:
        title = "Invalid Document Number"
        http_status = 422
        description = f"The document number in {field} is not a valid CPF or CNPJ."
        translation = "O CPF/CNPJ informado não é válido."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidDateTime(QIException):
    """Data com o formato certo que não existe no calendário (ex.: dia 30 de fevereiro)."""

    code = "QIT002003"

    def __init__(self, field) -> None:
        title = "Invalid Date Time"
        http_status = 422
        description = f"The value in {field} is not a real date and time."
        translation = "A data informada não existe."
        super().__init__(title, self.code, http_status, description, translation)


class AccountDataMismatch(QIException):
    """A conta já existe com outro documento ou outra data de abertura.

    A mensagem é genérica DE PROPÓSITO: não diz qual conta nem qual campo
    divergiu, pra que a resposta não sirva de oráculo a quem testa
    combinações de conta e documento. O detalhe fica no log.
    """

    code = "QIT002005"

    def __init__(self) -> None:
        title = "Account Data Mismatch"
        http_status = 422
        description = "The account data does not match the registered account."
        translation = "Os dados da conta não conferem com o cadastro."
        super().__init__(title, self.code, http_status, description, translation)


class NotFoundAccount(QIException):
    code = "QIT002006"

    def __init__(self, account_id) -> None:
        title = "Account not Found"
        http_status = 404
        description = f"Account with id {account_id} was not found."
        translation = f"A conta com id {account_id} não foi encontrada."
        super().__init__(title, self.code, http_status, description, translation)


class AccountAlreadyPermitted(QIException):
    code = "QIT002007"

    def __init__(self, account_id) -> None:
        title = "Account already permitted"
        http_status = 409
        description = f"Account with id {account_id} is not blocked."
        translation = "Essa conta não está bloqueada."
        super().__init__(title, self.code, http_status, description, translation)
