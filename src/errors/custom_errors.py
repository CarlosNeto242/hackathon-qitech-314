from errors import QIException


class NotFoundPixTransaction(QIException):
    code = "QIT001008"

    def __init__(self, pix_id) -> None:
        title = "Pix Transaction not Found"
        http_status = 404
        description = "Pix transaction was not found."
        translation = "O Pix não foi encontrado."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidPixDocumentNumber(QIException):
    code = "QIT001009"

    def __init__(self, field) -> None:
        title = "Invalid Document Number"
        http_status = 422
        description = "The document number is not a valid CPF or CNPJ."
        translation = "O CPF/CNPJ informado não é válido."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidDateTime(QIException):
    code = "QIT001010"

    def __init__(self, field) -> None:
        title = "Invalid Date Time"
        http_status = 422
        description = "The value in is not a real date and time."
        translation = "A data informada não existe."
        super().__init__(title, self.code, http_status, description, translation)


class AccountDataMismatch(QIException):
    code = "QIT001011"

    def __init__(self) -> None:
        title = "Account Data Mismatch"
        http_status = 422
        description = "The account data does not match the registered account."
        translation = "Os dados da conta não conferem com o cadastro."
        super().__init__(title, self.code, http_status, description, translation)


class NotFoundAccount(QIException):
    code = "QIT001012"

    def __init__(self, participant, branch, account_number) -> None:
        title = "Account not Found"
        http_status = 404
        description = "Account was not found."
        translation = "A conta não foi encontrada."
        super().__init__(title, self.code, http_status, description, translation)


class AccountAlreadyPermitted(QIException):
    code = "QIT001013"

    def __init__(self, participant, branch, account_number) -> None:
        title = "Account already permitted"
        http_status = 409
        description = "Account is not blocked."
        translation = "Essa conta não está bloqueada."
        super().__init__(title, self.code, http_status, description, translation)


class PixIdConflict(QIException):
    code = "QIT001014"

    def __init__(self, pix_id) -> None:
        title = "Pix id conflict"
        http_status = 409
        description = "Pix id was already used by a transaction with different content."
        translation = "Esse id de Pix já foi usado por outra transação, com outro conteúdo."
        super().__init__(title, self.code, http_status, description, translation)
