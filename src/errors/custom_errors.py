from errors import QIException


class NotFoundPixTransaction(QIException):
    code = "QIT002001"

    def __init__(self, pix_id) -> None:
        title = "Pix Transaction not Found"
        http_status = 404
        description = f"Pix transaction with id {pix_id} was not found."
        translation = f"O Pix com id {pix_id} não foi encontrado."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidPixDocumentNumber(QIException):
    code = "QIT002002"

    def __init__(self, field) -> None:
        title = "Invalid Document Number"
        http_status = 422
        description = f"The document number in {field} is not a valid CPF or CNPJ."
        translation = "O CPF/CNPJ informado não é válido."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidDateTime(QIException):
    code = "QIT002003"

    def __init__(self, field) -> None:
        title = "Invalid Date Time"
        http_status = 422
        description = f"The value in {field} is not a real date and time."
        translation = "A data informada não existe."
        super().__init__(title, self.code, http_status, description, translation)


class AccountDataMismatch(QIException):
    code = "QIT002005"

    def __init__(self) -> None:
        title = "Account Data Mismatch"
        http_status = 422
        description = "The account data does not match the registered account."
        translation = "Os dados da conta não conferem com o cadastro."
        super().__init__(title, self.code, http_status, description, translation)


class NotFoundAccount(QIException):
    code = "QIT002006"

    def __init__(self, participant, branch, account_number) -> None:
        title = "Account not Found"
        http_status = 404
        description = f"Account {participant}/{branch}/{account_number} was not found."
        translation = f"A conta {participant}/{branch}/{account_number} não foi encontrada."
        super().__init__(title, self.code, http_status, description, translation)


class AccountAlreadyPermitted(QIException):
    code = "QIT002007"

    def __init__(self, participant, branch, account_number) -> None:
        title = "Account already permitted"
        http_status = 409
        description = f"Account {participant}/{branch}/{account_number} is not blocked."
        translation = "Essa conta não está bloqueada."
        super().__init__(title, self.code, http_status, description, translation)


class PixIdConflict(QIException):
    code = "QIT002008"

    def __init__(self, pix_id) -> None:
        title = "Pix id conflict"
        http_status = 409
        description = f"Pix id {pix_id} was already used by a transaction with different content."
        translation = "Esse id de Pix já foi usado por outra transação, com outro conteúdo."
        super().__init__(title, self.code, http_status, description, translation)
