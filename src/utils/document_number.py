CPF_LENGTH = 11

CHECK_DIGIT_POSITIONS = [9, 10]


def is_valid_cpf(document_number: str) -> bool:
    digits = []
    for character in document_number:
        if character.isdigit():
            digits.append(int(character))

    if len(digits) != CPF_LENGTH:
        return False

    all_digits_are_equal = True
    for digit in digits:
        if digit != digits[0]:
            all_digits_are_equal = False
            break

    if all_digits_are_equal:
        return False

    for position in CHECK_DIGIT_POSITIONS:
        total = 0
        first_weight = position + 1

        for index in range(position):
            total = total + digits[index] * (first_weight - index)

        remainder = total % 11

        if remainder < 2:
            expected_digit = 0
        else:
            expected_digit = 11 - remainder

        if digits[position] != expected_digit:
            return False

    return True


CNPJ_LENGTH = 14


CNPJ_FIRST_WEIGHTS = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
CNPJ_SECOND_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def only_digits(document_number: str) -> str:
    return "".join(character for character in document_number if character.isdigit())


def is_valid_cnpj(document_number: str) -> bool:
    digits = [int(character) for character in only_digits(document_number)]

    if len(digits) != CNPJ_LENGTH:
        return False

    if len(set(digits)) == 1:
        return False

    for weights in (CNPJ_FIRST_WEIGHTS, CNPJ_SECOND_WEIGHTS):
        position = len(weights)
        total = sum(digit * weight for digit, weight in zip(digits, weights))
        remainder = total % 11

        if remainder < 2:
            expected_digit = 0
        else:
            expected_digit = 11 - remainder

        if digits[position] != expected_digit:
            return False

    return True


def is_valid_document(document_number: str) -> bool:
    digits = only_digits(document_number)

    if len(digits) == CPF_LENGTH:
        return is_valid_cpf(digits)

    if len(digits) == CNPJ_LENGTH:
        return is_valid_cnpj(digits)

    return False
