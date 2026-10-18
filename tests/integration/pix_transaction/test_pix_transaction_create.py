from copy import deepcopy
from uuid import UUID

from tests.utils import PayloadGenerator, RandomGenerator, RequestGenerator
from tests.utils.requisition import ClientRequisition


class TestPixTransactionCreate:
    def test_approves_valid_pix(self):
        payload = PayloadGenerator.create_pix_transaction_payload()

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 201
        assert UUID(response["key"])
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
        assert response["status"] == "approved"

    def test_geolocation_is_optional(self):
        """Sem o campo e com o campo nulo: os dois são "não veio localização"."""
        sem_campo = PayloadGenerator.create_pix_transaction_payload()
        del sem_campo["source"]["geolocation"]

        campo_nulo = PayloadGenerator.create_pix_transaction_payload()
        campo_nulo["source"]["geolocation"] = None

        for payload in (sem_campo, campo_nulo):
            status, response = RequestGenerator.POST_pix_transaction(payload)
            assert status == 201
            assert response["status"] == "approved"


class TestPixTransactionSchema:
    """Payload que não se consegue ler: 400, e nada é gravado."""

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
        """Cada volta do laço tira UM campo obrigatório e mantém os outros."""
        caminhos_obrigatorios = [
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

        for caminho in caminhos_obrigatorios:
            payload = PayloadGenerator.create_pix_transaction_payload()
            alvo = payload
            for parte in caminho[:-1]:
                alvo = alvo[parte]
            del alvo[caminho[-1]]

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 400, f"aceitou o payload sem {'.'.join(caminho)}"
            assert response["code"] == "QIT000001"

    def test_refuses_non_positive_amount(self):
        for amount in (0, -100):
            payload = PayloadGenerator.create_pix_transaction_payload(amount=amount)

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 400, f"aceitou amount={amount}"

    def test_refuses_date_without_timezone(self):
        """Sem fuso, "22:15" pode ser qualquer um de vários instantes."""
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["transaction_date"] = "2026-10-17T22:15:00"

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 400

    def test_refuses_id_longer_than_16(self):
        payload = PayloadGenerator.create_pix_transaction_payload(pix_id="p" * 17)

        status, _response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 400

    def test_refuses_malformed_document_number(self):
        formatos_invalidos = [
            "1234567890",  # 10 dígitos
            "123456789012",  # 12 dígitos
            "123.456789-09",  # máscara de CPF pela metade
            "12345678/0001-90",  # máscara de CNPJ pela metade
            "123.456.789/09",  # separador errado
            "abc.def.ghi-jk",
            "",
        ]
        for documento in formatos_invalidos:
            payload = PayloadGenerator.create_pix_transaction_payload()
            payload["source_account"]["owner"]["document_number"] = documento

            status, _response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 400, f"aceitou o documento {documento!r}"

    def test_refuses_partial_geolocation(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["source"]["geolocation"] = {"latitude": -23.56}

        status, response = RequestGenerator.POST_pix_transaction(payload)

        assert status == 400


class TestPixTransactionImpossibleValues:
    """Formato certo, valor que não pode existir: 422."""

    def test_refuses_impossible_dates(self):
        campos = [
            ("transaction_date",),
            ("source_account", "opening_date"),
            ("destination_account", "opening_date"),
        ]

        for caminho in campos:
            payload = PayloadGenerator.create_pix_transaction_payload()
            alvo = payload
            for parte in caminho[:-1]:
                alvo = alvo[parte]
            alvo[caminho[-1]] = "2026-02-30T10:00:00-03:00"

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 422, f"aceitou 30 de fevereiro em {'.'.join(caminho)}"
            assert response["code"] == "QIT002003"

    def test_refuses_invalid_ip(self):
        """Quem recusa é o schema ("format" ipv4/ipv6), então é 400. Sem isso,
        o valor chegaria à coluna INET e o Postgres responderia com um 500."""
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
        for papel in ("source_account", "destination_account"):
            payload = PayloadGenerator.create_pix_transaction_payload()
            payload[papel]["owner"]["document_number"] = "111.222.333-44"

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 422, f"aceitou CPF inválido em {papel}"
            assert response["code"] == "QIT002002"

    def test_refuses_invalid_cnpj_check_digits(self):
        """Mesma conta do CPF, com os pesos do CNPJ. Inclui o CNPJ de dígitos
        todos iguais, que passa na conta e mesmo assim não existe."""
        for documento in ("11.222.333/0001-80", "11111111111111"):
            payload = PayloadGenerator.create_pix_transaction_payload(destination_document_number=documento)

            status, response = RequestGenerator.POST_pix_transaction(payload)

            assert status == 422, f"aceitou o CNPJ {documento}"
            assert response["code"] == "QIT002002"

    def test_invalid_pix_is_not_recorded(self):
        payload = PayloadGenerator.create_pix_transaction_payload()
        payload["transaction_date"] = "2026-02-30T10:00:00-03:00"

        status, _response = RequestGenerator.POST_pix_transaction(payload)
        assert status == 422

        status, _response = RequestGenerator.GET_pix_transaction(payload["id"])
        assert status == 404


class TestPixTransactionAccountData:
    """A mesma conta em dois Pix: o cadastro gravado e o payload têm que bater."""

    def test_same_document_with_and_without_punctuation(self):
        primeiro = PayloadGenerator.create_pix_transaction_payload()
        segundo = PayloadGenerator.create_pix_transaction_payload()
        segundo["source_account"] = deepcopy(primeiro["source_account"])

        documento = primeiro["source_account"]["owner"]["document_number"]
        segundo["source_account"]["owner"]["document_number"] = documento.replace(".", "").replace("-", "")

        for payload in (primeiro, segundo):
            status, _response = RequestGenerator.POST_pix_transaction(payload)
            assert status == 201

    def test_same_opening_date_in_another_timezone(self):
        """10:00 em -03:00 e 13:00 em UTC são o mesmo instante, não divergência."""
        primeiro = PayloadGenerator.create_pix_transaction_payload()
        segundo = PayloadGenerator.create_pix_transaction_payload()
        segundo["source_account"] = deepcopy(primeiro["source_account"])
        segundo["source_account"]["opening_date"] = "2025-03-02T13:00:00Z"

        for payload in (primeiro, segundo):
            status, _response = RequestGenerator.POST_pix_transaction(payload)
            assert status == 201

    def test_refuses_divergent_account_data(self):
        """Documento ou data de abertura diferentes do cadastro: 422 genérico,
        e o Pix não fica gravado."""
        divergencias = [
            ("source_account", "owner", "document_number", RandomGenerator.generate_cpf()),
            ("source_account", "opening_date", "2024-01-01T10:00:00-03:00"),
            ("destination_account", "owner", "document_number", RandomGenerator.generate_cpf()),
            ("destination_account", "opening_date", "2024-01-01T10:00:00-03:00"),
        ]

        for *caminho, valor in divergencias:
            primeiro = PayloadGenerator.create_pix_transaction_payload()
            status, _response = RequestGenerator.POST_pix_transaction(primeiro)
            assert status == 201

            segundo = PayloadGenerator.create_pix_transaction_payload()
            papel = caminho[0]
            segundo[papel] = deepcopy(primeiro[papel])
            alvo = segundo
            for parte in caminho[:-1]:
                alvo = alvo[parte]
            alvo[caminho[-1]] = valor

            status, response = RequestGenerator.POST_pix_transaction(segundo)
            assert status == 422, f"aceitou divergência em {'.'.join(caminho)}"
            assert response["code"] == "QIT002005"

            status, _response = RequestGenerator.GET_pix_transaction(segundo["id"])
            assert status == 404

    def test_source_participant_from_payload_is_ignored(self):
        """A origem é sempre deste banco: o participant que vier no payload não
        cria uma conta nova. Prova: a mesma agência e conta com outro
        participant e outro CPF caem na MESMA linha, e dão divergência."""
        primeiro = PayloadGenerator.create_pix_transaction_payload()
        primeiro["source_account"]["participant"] = "11111111"
        status, _response = RequestGenerator.POST_pix_transaction(primeiro)
        assert status == 201

        segundo = PayloadGenerator.create_pix_transaction_payload()
        segundo["source_account"] = deepcopy(primeiro["source_account"])
        segundo["source_account"]["participant"] = "22222222"
        segundo["source_account"]["owner"]["document_number"] = RandomGenerator.generate_cpf()

        status, response = RequestGenerator.POST_pix_transaction(segundo)
        assert status == 422
        assert response["code"] == "QIT002005"
