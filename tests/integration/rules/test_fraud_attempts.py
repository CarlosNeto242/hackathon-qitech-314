"""Testes de ataque: o motor visto por quem quer fraudá-lo.

Cada teste encena uma técnica de fraude de Pix e afirma o comportamento
SEGURO. Os que o motor ainda não segura estão marcados com xfail e o motivo:
a suíte continua verde, mas cada brecha fica documentada. Com strict=True, o
xfail falha quando a brecha for fechada, lembrando de tirar a marcação.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from tests.utils import DbUtils, PixJourney, RandomGenerator, RequestGenerator
from tests.utils.pix_journey import DICT_MARKED_DOCUMENT, RECIFE

BLOCKED_STATUSES = ("rejected", "two_factor_required")


def pego_no_destino(reasons: list) -> bool:
    """O laranja foi pego por alguma regra do DESTINO (ou já estava bloqueado).

    O 2FA de aparelho novo do pagador não conta: na vida real os pagadores
    são clientes antigos, com aparelho conhecido. A pergunta é se o motor
    enxerga o recebedor."""
    return reasons == ["ACCOUNT_BLOCKED"] or any(reason.startswith("DEST_") for reason in reasons)


def conta_id(conta: dict) -> int:
    return DbUtils.account_id(conta["branch"], conta["account_number"])


def vitima_antiga(valor_habitual: int = 10_000) -> dict:
    """Um cliente legítimo e antigo: conta de 2025, 30 Pix de R$ 100 nos
    últimos dias, sempre pelo mesmo aparelho. É a conta que o fraudador vai
    tentar esvaziar."""
    first = PixJourney.new(amount=valor_habitual)
    PixJourney.send(first)
    DbUtils.seed_sent(
        conta_id(first["source_account"]),
        conta_id(first["destination_account"]),
        count=30,
        amount=valor_habitual,
        days_ago=10,
        device_id=first["source"]["device_id"],
    )
    return first


class TestAccountTakeover:
    """O fraudador entrou na conta da vítima (senha vazada, golpe da central)."""

    @pytest.mark.xfail(strict=True, reason='BRECHA (limitação conhecida): device_id e geolocalização são autodeclarados. Com o aparelho clonado e sem localização, só sobram o limite de valor e a velocidade')
    def test_cloned_device_without_location_drains_the_account(self):
        """Com o device_id da vítima (clonado por malware) e sem mandar
        localização, o fraudador faz um Pix logo abaixo do limite de valor."""
        vitima = vitima_antiga()

        ataque = PixJourney.from_same_source(vitima, amount=199_900)
        ataque["source"]["geolocation"] = None
        status, _reasons = PixJourney.send(ataque)

        assert status in BLOCKED_STATUSES

    def test_new_device_far_from_the_victim_is_stopped(self):
        """Sem clonar o aparelho: celular do fraudador, em outra cidade."""
        vitima = vitima_antiga()

        ataque = PixJourney.from_same_source(vitima, amount=50_000)
        ataque["source"]["device_id"] = "dvc-fraudador"
        ataque["source"]["geolocation"] = RECIFE
        status, reasons = PixJourney.send(ataque)

        assert status == "rejected"
        assert "SRC_LOCATION_MISMATCH" in reasons

    @pytest.mark.xfail(strict=True, reason='BRECHA: Pix com 2FA nunca confirmado entra no perfil de valor (premissa de que o 2FA foi cumprido), e o fraudador infla o percentil insistindo')
    def test_unconfirmed_2fa_inflates_the_amount_profile(self):
        """O fraudador não tem o 2FA da vítima, mas insiste, devagar pra não
        cair na velocidade: 3 Pix de R$ 10.000 na última meia hora, todos com
        2FA, nenhum confirmado. O motor conta esses Pix como "valor habitual"
        (premissa: 2FA cumprido) e o percentil 95 da conta vai de R$ 100 pra
        R$ 10.000. Um Pix de R$ 14.000 passa sem atrito."""
        vitima = vitima_antiga()
        DbUtils.seed_sent(
            conta_id(vitima["source_account"]),
            conta_id(vitima["destination_account"]),
            count=3,
            amount=1_000_000,
            minutes_ago=30,
            device_id=vitima["source"]["device_id"],
            two_factor_reason="SRC_HIGH_AMOUNT",
        )

        status, _reasons = PixJourney.send(PixJourney.from_same_source(vitima, amount=1_400_000))

        assert status in BLOCKED_STATUSES

    def test_parallel_burst_does_not_beat_velocity(self):
        """Disparar 15 Pix ao mesmo tempo, esperando que as análises não se
        enxerguem: no máximo os primeiros passam sem atrito."""
        vitima = vitima_antiga()
        ataques = [PixJourney.from_same_source(vitima) for _ in range(15)]

        with ThreadPoolExecutor(max_workers=15) as executor:
            results = list(executor.map(PixJourney.send, ataques))

        aprovados = [result for result in results if result[0] == "approved"]
        assert len(aprovados) <= 3
        assert any(status == "rejected" for status, _reasons in results)


class TestStructuring:
    """Fracionamento: muitos Pix pequenos no lugar de um grande."""

    @pytest.mark.xfail(strict=True, reason='BRECHA: não há limite de soma enviada numa janela; só o valor de cada Pix e a velocidade de 3 minutos')
    def test_many_pix_just_below_the_limit_spread_over_time(self):
        """50 Pix de R$ 1.999 na última meia hora (R$ 99.950), sempre abaixo do
        limite por Pix e devagar o bastante pra não contar como rajada. O
        próximo de R$ 1.999 continua passando."""
        vitima = vitima_antiga()
        DbUtils.seed_sent(
            conta_id(vitima["source_account"]),
            conta_id(vitima["destination_account"]),
            count=50,
            amount=199_900,
            minutes_ago=30,
            device_id=vitima["source"]["device_id"],
        )

        status, _reasons = PixJourney.send(PixJourney.from_same_source(vitima, amount=199_900))

        assert status in BLOCKED_STATUSES


class TestMuleNetwork:
    """Contas laranja recebendo o dinheiro das vítimas."""

    def test_spreading_across_accounts_of_the_same_document(self):
        """Um laranja com 12 contas (o mesmo CPF): 12 vítimas pagam no mesmo
        segundo, cada uma numa conta. Nenhuma conta passa do limite de rajada."""
        documento = RandomGenerator.generate_cpf()
        results = [PixJourney.send(PixJourney.new(destination_document_number=documento)) for _ in range(12)]

        assert any(pego_no_destino(reasons) for _status, reasons in results)

    def test_aged_mule_receiving_slow_and_steady(self):
        """Laranja paciente: espera a conta passar de 5 dias e recebe de 300
        pagadores diferentes na última meia hora, sem nunca passar de 10 por
        minuto."""
        first = PixJourney.new()
        first["destination_account"]["opening_date"] = PixJourney.days_ago(6)
        PixJourney.send(first)
        DbUtils.seed_received_from_distinct_payers(
            conta_id(first["destination_account"]), 300, 50_000, minutes_ago=5
        )

        _status, reasons = PixJourney.send(PixJourney.to_same_destination(first))

        assert pego_no_destino(reasons)

    @pytest.mark.xfail(strict=True, reason='BRECHA (limitação conhecida): a opening_date do destino vem do primeiro payload que cita a conta; em produção viria do DICT')
    def test_mule_registered_with_a_false_opening_date(self):
        """A conta laranja foi aberta ontem, mas o primeiro Pix que a menciona
        diz que ela existe desde 2020. O motor guarda a primeira versão, e a
        regra de conta nova nunca dispara."""
        first = PixJourney.new()
        first["destination_account"]["opening_date"] = "2020-01-01T10:00:00-03:00"
        PixJourney.send(first)
        DbUtils.seed_received_from_distinct_payers(
            conta_id(first["destination_account"]), 60, 50_000, minutes_ago=10
        )

        _status, reasons = PixJourney.send(PixJourney.to_same_destination(first))

        assert pego_no_destino(reasons)

    @pytest.mark.xfail(strict=True, reason='BRECHA (limitação conhecida): o bloqueio é por conta, não por documento')
    def test_blocked_mule_moves_to_another_account(self):
        """A conta laranja foi bloqueada por reincidência; dias depois, o dono
        abre outra conta, com o mesmo CPF, e volta a receber. (Os Pix da
        primeira conta são envelhecidos em 1 dia: sem isso, a conta nova seria
        pega pela velocidade contada por documento, e não pelo bloqueio.)"""
        documento = RandomGenerator.generate_cpf()
        first = PixJourney.new(destination_document_number=documento)
        PixJourney.send(first)
        for _ in range(30):
            status, reasons = PixJourney.send(PixJourney.to_same_destination(first))
            if reasons == ["ACCOUNT_BLOCKED"]:
                break
        assert reasons == ["ACCOUNT_BLOCKED"], "a primeira conta deveria ter sido bloqueada"
        DbUtils.age_received(conta_id(first["destination_account"]), days=1)

        _status, reasons = PixJourney.send(PixJourney.new(destination_document_number=documento))

        assert pego_no_destino(reasons)

    def test_marked_document_with_another_formatting(self):
        """Tentar escapar do DICT mandando o documento marcado sem máscara."""
        sem_mascara = DICT_MARKED_DOCUMENT.replace(".", "").replace("-", "")

        status, reasons = PixJourney.send(PixJourney.new(destination_document_number=sem_mascara))

        assert (status, reasons) == ("rejected", ["DEST_FRAUD_MARKED"])


class TestShellCompany:
    @pytest.mark.xfail(strict=True, reason='BRECHA: a origem não tem regra de idade de conta; um CNPJ aberto ontem tem o mesmo limite de R$ 100.000 por Pix de uma empresa antiga')
    def test_day_old_company_moves_large_amounts(self):
        """Empresa de fachada aberta ontem: depois do primeiro Pix (2FA do
        aparelho), manda R$ 99.999 sem nenhum atrito."""
        first = PixJourney.new(source_document_number=RandomGenerator.generate_cnpj())
        first["source_account"]["opening_date"] = PixJourney.days_ago(1)
        PixJourney.send(first)

        status, _reasons = PixJourney.send(PixJourney.from_same_source(first, amount=9_999_900))

        assert status in BLOCKED_STATUSES


class TestApiAbuse:
    """Ataques à própria API, não às regras."""

    def test_replay_of_an_approved_pix_id_with_other_content(self):
        """Um Pix pequeno é aprovado. O atacante reenvia o MESMO id com outro
        valor e outro destino (marcado no DICT), esperando receber de volta o
        "approved" do Pix original. A API recusa: mesmo id, outro conteúdo."""
        vitima = vitima_antiga()
        legitimo = PixJourney.from_same_source(vitima)
        status, _reasons = PixJourney.send(legitimo)
        assert status == "approved"

        adulterado = PixJourney.from_same_source(
            vitima, pix_id=legitimo["id"], amount=100_000_000, destination_document_number=DICT_MARKED_DOCUMENT
        )
        status_code, response = RequestGenerator.POST_pix_transaction(adulterado)

        assert status_code == 409
        assert response["code"] == "QIT002008"

    def test_amount_beyond_the_database_limit(self):
        """Valor maior que o maior inteiro do banco: tem que ser recusado como
        payload inválido, não derrubar a API com 500."""
        payload = PixJourney.new(amount=10**19)

        status_code, response = RequestGenerator.POST_pix_transaction(payload)

        assert status_code == 400
        assert response["code"] == "QIT000001"

    def test_client_clock_does_not_move_the_windows(self):
        """Mandar transaction_date espaçadas de uma hora pra parecer que os Pix
        não chegaram juntos: as janelas usam o horário do servidor."""
        first = PixJourney.new()
        first["transaction_date"] = "2026-10-17T08:00:00-03:00"
        results = [PixJourney.send(first)]
        for hora in range(9, 12):
            payload = PixJourney.to_same_destination(first)
            payload["transaction_date"] = f"2026-10-17T{hora:02d}:00:00-03:00"
            results.append(PixJourney.send(payload))

        assert results[3] == ("rejected", ["DEST_RECEIVING_VELOCITY"])

    @pytest.mark.xfail(strict=True, reason='BRECHA (limitação conhecida): o primeiro payload define o cadastro do destino; quem chega primeiro com o CPF errado faz os Pix legítimos seguintes darem 422')
    def test_poisoning_a_victim_account_with_a_wrong_document(self):
        """O atacante manda o primeiro Pix pra conta de uma vítima com o CPF
        errado. A versão errada fica gravada, e o Pix legítimo seguinte para
        ela, com o CPF certo, é recusado."""
        conta_da_vitima = PixJourney.new()["destination_account"]
        cpf_verdadeiro = conta_da_vitima["owner"]["document_number"]

        envenenado = PixJourney.new()
        envenenado["destination_account"] = deepcopy(conta_da_vitima)
        envenenado["destination_account"]["owner"]["document_number"] = RandomGenerator.generate_cpf()
        PixJourney.send(envenenado)

        legitimo = PixJourney.new()
        legitimo["destination_account"] = deepcopy(conta_da_vitima)
        legitimo["destination_account"]["owner"]["document_number"] = cpf_verdadeiro
        status_code, _response = RequestGenerator.POST_pix_transaction(legitimo)

        assert status_code == 201
