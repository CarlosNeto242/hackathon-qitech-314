from copy import deepcopy
from uuid import UUID

from tests.utils import PayloadGenerator, RandomGenerator, RequestGenerator
from tests.utils.requisition import ClientRequisition


def from_same_source_and_device(first_payload: dict) -> dict:
    payload = PayloadGenerator.create_pix_transaction_payload()
    payload["source_account"] = deepcopy(first_payload["source_account"])
    payload["source"]["device_id"] = first_payload["source"]["device_id"]
    return payload


class TestPixTransactionCreate:
    def test_first_pix_of_account_requires_2fa(self):
        payload = PayloadGenerator.create_pix_transaction_payload()

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201
        assert UUID(response["key"])
        assert response["status"] == "two_factor_required"
        assert response["metadata"] == {"reasons": ["SRC_NEW_DEVICE"]}

    def test_approves_pix_from_recognized_device(self):
        first_payload = PayloadGenerator.create_pix_transaction_payload()
        status, _response = RequestGenerator.POST_pix_transaction(first_payload)
        assert status == 201

        status, response = RequestGenerator.POST_pix_transaction(from_same_source_and_device(first_payload))

        assert status == 201
        assert response["status"] == "approved"
        assert response["metadata"] == {}

    def test_requires_internal_token(self):
        payload = PayloadGenerator.create_pix_transaction_payload()

        response = ClientRequisition.send("POST", "/pix/transaction", payload=payload)

        assert response.response_status == 403
        assert response.response_json["code"] == "QIT000002"

    def test_accepts_cnpj(self):
        payload = PayloadGenerator.create_pix_transaction_payload(
            source_document_number=RandomGenerator.generate_cnpj(),
            destination_document_number=RandomGenerator.generate_cnpj(),
        )

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201
        assert response["metadata"] == {"reasons": ["SRC_NEW_DEVICE"]}

    def test_geolocation_is_optional(self):
        missing_field = PayloadGenerator.create_pix_transaction_payload()
        del missing_field["source"]["geolocation"]

        null_field = PayloadGenerator.create_pix_transaction_payload()
        null_field["source"]["geolocation"] = None

        for payload in (missing_field, null_field):
            status, response = RequestGenerator.POST_pix_transaction(payload)
            assert status == 201
            assert response["metadata"] == {"reasons": ["SRC_NEW_DEVICE"]}


class TestPixTransactionSchema:
    def test_refuses_empty_body(self):
        status, response = RequestGenerator.POST_pix_transaction({})

        assert status == 400
        assert response["code"] == "QIT000001"

    def test_refuses_unknown_field(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["campo_que_nao_existe"] = 1

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 400
        assert response["code"] == "QIT000001"

    def test_refuses_missing_required_fields(self):
        required_paths = [
            ("id",),
            ("amount",),
            ("transaction_date",),
            ("source_account",),
            ("destination_account",),
            ("source",),
            ("source_account", "owner"),
            ("destination_account", "participant"),
            ("source", "device_id"),
            ("source", "channel"),
            ("source", "ip"),
        ]

        for field_path in required_paths:
            payload = PayloadGenerator.create_pix_transaction_payload()
            target = payload
            for part in field_path[:-1]:
                target = target[part]
            del target[field_path[-1]]

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 400, f"aceitou o payload sem {'.'.join(field_path)}"
            assert response["code"] == "QIT000001"

    def test_refuses_non_positive_amount(self):
        for amount in (0, -100):
            payload = PayloadGenerator.create_pix_transaction_payload(amount=amount)

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 400, f"aceitou amount={amount}"

    def test_refuses_date_without_timezone(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["transaction_date"] = "2026-10-17T22:15:00"

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 400

    def test_refuses_id_longer_than_16(self):
        payload = PayloadGenerator.create_pix_transaction_payload(pix_id="p" * 17)

        status, _response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 400

    def test_refuses_malformed_document_number(self):
        invalid_formats = [
            "1234567890",
            "123456789012",
            "123.456789-09",
            "12345678/0001-90",
            "123.456.789/09",
            "abc.def.ghi-jk",
            "",
        ]
        for document in invalid_formats:
            payload = PayloadGenerator.create_pix_transaction_payload()
            payload["source_account"]["owner"]["document_number"] = document

            status, _response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 400, f"aceitou o documento {document!r}"

    def test_refuses_partial_geolocation(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["source"]["geolocation"] = {"latitude": -23.56}

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 400


class TestPixTransactionImpossibleValues:
    def test_refuses_impossible_dates(self):
        fields = [
            ("transaction_date",),
            ("source_account", "opening_date"),
            ("destination_account", "opening_date"),
        ]

        for field_path in fields:
            payload = PayloadGenerator.create_pix_transaction_payload()
            target = payload
            for part in field_path[:-1]:
                target = target[part]
            target[field_path[-1]] = "2026-02-30T10:00:00-03:00"

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 422, f"aceitou 30 de fevereiro em {'.'.join(field_path)}"
            assert response["code"] == "QIT002003"

    def test_refuses_invalid_ip(self):
        for ip in ("999.1.1.1", "nao-e-ip", "", "1.2.3"):
            payload = PayloadGenerator.create_pix_transaction_payload()
            payload["source"]["ip"] = ip

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 400, f"aceitou o IP {ip!r}"
            assert response["code"] == "QIT000001"

    def test_accepts_ipv6(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["source"]["ip"] = "2001:db8::1"

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201

    def test_refuses_invalid_document_check_digits(self):
        for role in ("source_account", "destination_account"):
            payload = PayloadGenerator.create_pix_transaction_payload()
            payload[role]["owner"]["document_number"] = "111.222.333-44"

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 422, f"aceitou CPF inválido em {role}"
            assert response["code"] == "QIT002002"

    def test_refuses_invalid_cnpj_check_digits(self):
        for document in ("11.222.333/0001-80", "11111111111111"):
            payload = PayloadGenerator.create_pix_transaction_payload(destination_document_number=document)

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 422, f"aceitou o CNPJ {document}"
            assert response["code"] == "QIT002002"

    def test_invalid_pix_is_not_recorded(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["transaction_date"] = "2026-02-30T10:00:00-03:00"

        status, _response = RequestGenerator.POST_pix_transaction(payload)
        assert status == 422

        status, _response = RequestGenerator.GET_pix_transaction(payload["id"])
        assert status == 404


class TestPixTransactionAccountData:
    def test_same_document_with_and_without_punctuation(self):
        first_payload = PayloadGenerator.create_pix_transaction_payload()
        second_payload = PayloadGenerator.create_pix_transaction_payload()
        second_payload["source_account"] = deepcopy(first_payload["source_account"])

        document = first_payload["source_account"]["owner"]["document_number"]
        second_payload["source_account"]["owner"]["document_number"] = document.replace(".", "").replace("-", "")

        for payload in (first_payload, second_payload):
            status, _response = RequestGenerator.POST_pix_transaction(payload)
            assert status == 201

    def test_same_opening_date_in_another_timezone(self):
        first_payload = PayloadGenerator.create_pix_transaction_payload()
        second_payload = PayloadGenerator.create_pix_transaction_payload()
        second_payload["source_account"] = deepcopy(first_payload["source_account"])
        second_payload["source_account"]["opening_date"] = "2025-03-02T13:00:00Z"

        for payload in (first_payload, second_payload):
            status, _response = RequestGenerator.POST_pix_transaction(payload)
            assert status == 201

    def test_refuses_divergent_account_data(self):
        divergences = [
            ("source_account", "owner", "document_number", RandomGenerator.generate_cpf()),
            ("source_account", "opening_date", "2024-01-01T10:00:00-03:00"),
            ("destination_account", "owner", "document_number", RandomGenerator.generate_cpf()),
            ("destination_account", "opening_date", "2024-01-01T10:00:00-03:00"),
        ]

        for *field_path, value in divergences:
            first_payload = PayloadGenerator.create_pix_transaction_payload()
            status, _response = RequestGenerator.POST_pix_transaction(first_payload)
            assert status == 201

            second_payload = PayloadGenerator.create_pix_transaction_payload()
            role = field_path[0]
            second_payload[role] = deepcopy(first_payload[role])
            target = second_payload
            for part in field_path[:-1]:
                target = target[part]
            target[field_path[-1]] = value

            status, response = RequestGenerator.POST_pix_transaction(second_payload)
            assert status == 422, f"aceitou divergência em {'.'.join(field_path)}"
            assert response["code"] == "QIT002005"

            status, _response = RequestGenerator.GET_pix_transaction(second_payload["id"])
            assert status == 404

    def test_source_participant_from_payload_is_ignored(self):
        first_payload = PayloadGenerator.create_pix_transaction_payload()
        first_payload["source_account"]["participant"] = "11111111"
        status, _response = RequestGenerator.POST_pix_transaction(first_payload)
        assert status == 201

        second_payload = PayloadGenerator.create_pix_transaction_payload()
        second_payload["source_account"] = deepcopy(first_payload["source_account"])
        second_payload["source_account"]["participant"] = "22222222"
        second_payload["source_account"]["owner"]["document_number"] = RandomGenerator.generate_cpf()

        status, response = RequestGenerator.POST_pix_transaction(second_payload)
        assert status == 422
        assert response["code"] == "QIT002005"
