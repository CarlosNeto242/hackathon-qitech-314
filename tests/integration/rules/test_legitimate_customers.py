"""Testes de falso positivo: o motor visto por quem só quer pagar.

Cada teste encena a rotina de um cliente legítimo e afirma o que ele deveria
receber, sem olhar como as regras foram escritas:

  - comportamento habitual  → approved;
  - legítimo mas incomum    → no máximo 2FA.

FALSO POSITIVO é REJEITAR um cliente legítimo: é isso que o enunciado chama de
"travar quem só quer pagar". Hoje não há nenhum conhecido. Se aparecer, marque
o teste com xfail(strict=True) e o motivo: o xfail falha quando o falso
positivo for corrigido.

2FA num cliente legítimo é ATRITO, não falso positivo: ele confirma e o Pix
segue. Os testes aceitam o 2FA, mas os atritos conhecidos estão anotados no
docstring de cada um (2FA demais na rotina acostuma o cliente a confirmar sem
ler, que é o hábito que o golpe da falsa central explora).
"""

import time

from tests.utils import DbUtils, PixJourney, RandomGenerator
from tests.utils.pix_journey import RECIFE, SAO_PAULO

ACCEPTABLE = ("approved", "two_factor_required")


def travados(results: list) -> list:
    """Os Pix que não foram aprovados, como (posição, status, motivos)."""
    return [(n, status, reasons) for n, (status, reasons) in enumerate(results, start=1) if status != "approved"]


def recusados(results: list) -> list:
    """Os Pix rejeitados, como (posição, motivos)."""
    return [(n, reasons) for n, (status, reasons) in enumerate(results, start=1) if status == "rejected"]


def conta_id(conta: dict) -> int:
    return DbUtils.account_id(conta["branch"], conta["account_number"])


def cliente(payload: dict = None, **kwargs) -> dict:
    """Um cliente com aparelho conhecido: o primeiro Pix (2FA do aparelho
    novo) foi ontem. Os Pix seguintes dele, pelo mesmo aparelho, representam
    a rotina normal, e o de ontem não conta nas janelas de velocidade."""
    first = payload or PixJourney.new(**kwargs)
    PixJourney.send(first)
    DbUtils.age_transaction(first["id"], days=1)
    return first


def com_historico(first: dict, count: int, amount: int, days_ago: int) -> None:
    """Planta Pix aprovados antigos do cliente, pelo aparelho dele."""
    DbUtils.seed_sent(
        conta_id(first["source_account"]),
        conta_id(first["destination_account"]),
        count=count,
        amount=amount,
        days_ago=days_ago,
        device_id=first["source"]["device_id"],
    )


class TestEverydayPayments:
    def test_paying_the_rent_every_month(self):
        """Cliente antigo: Pix pequenos no dia a dia e o aluguel de R$ 2.500
        todo mês. O aluguel deste mês é rotina.

        ATRITO conhecido: hoje pede 2FA todo mês (o aluguel fica acima de
        1,5x o p95). Não é falso positivo: o Pix não é recusado.
        """
        pagador = cliente()
        com_historico(pagador, count=30, amount=10_000, days_ago=20)
        com_historico(pagador, count=1, amount=250_000, days_ago=60)
        com_historico(pagador, count=1, amount=250_000, days_ago=30)

        status, reasons = PixJourney.send(PixJourney.from_same_source(pagador, amount=250_000))

        assert status in ACCEPTABLE

    def test_salary_from_the_employer(self):
        """A empresa paga o salário de um funcionário."""
        empresa = cliente(source_document_number=RandomGenerator.generate_cnpj())

        status, reasons = PixJourney.send(PixJourney.from_same_source(empresa, amount=450_000))

        assert (status, reasons) == ("approved", [])

    def test_sending_money_to_family_a_few_times(self):
        """Três Pix seguidos pra mãe: um pro mercado, um pra farmácia, um pro gás."""
        filho = cliente()
        mae = PixJourney.from_same_source(filho)
        results = [PixJourney.send(mae)]
        for _ in range(2):
            results.append(PixJourney.send(PixJourney.between_same_accounts(mae)))

        assert results == [("approved", [])] * 3

    def test_paying_the_monthly_bills_in_a_row(self):
        """Dia 5: aluguel, luz, água, internet e condomínio, um atrás do outro,
        cada um pra uma empresa diferente.

        ATRITO conhecido: a velocidade de envio pede 2FA a partir do 4º
        Pix seguido.
        """
        pagador = cliente()

        results = [PixJourney.send(PixJourney.from_same_source(pagador, amount=30_000)) for _ in range(5)]

        assert recusados(results) == []

    def test_location_off_and_changing_networks(self):
        """O cliente desliga a localização e alterna entre Wi-Fi de casa e 4G."""
        pagador = cliente()
        sem_gps = PixJourney.from_same_source(pagador)
        sem_gps["source"]["geolocation"] = None
        sem_gps["source"]["ip"] = "203.0.113.77"

        status, reasons = PixJourney.send(sem_gps)

        assert (status, reasons) == ("approved", [])


class TestUnusualButLegitimate:
    def test_new_phone(self):
        """Celular novo: confirmar a identidade uma vez é razoável; depois disso,
        o cliente volta a pagar sem atrito."""
        pagador = cliente()
        celular_novo = PixJourney.from_same_source(pagador)
        celular_novo["source"]["device_id"] = "dvc-celular-novo"

        status, _reasons = PixJourney.send(celular_novo)
        assert status == "two_factor_required"

        status, reasons = PixJourney.send(PixJourney.from_same_source(celular_novo))
        assert (status, reasons) == ("approved", [])

    def test_one_off_large_purchase(self):
        """Cliente sem histórico compra um celular de R$ 3.000: no máximo uma
        confirmação."""
        pagador = cliente()

        status, _reasons = PixJourney.send(PixJourney.from_same_source(pagador, amount=300_000))

        assert status in ACCEPTABLE

    def test_flying_to_another_city(self):
        """Pix em São Paulo de manhã, voo de 5 h, Pix em Recife à tarde
        (2.100 km em 5 h: 420 km/h, velocidade de avião)."""
        pagador = PixJourney.new()
        pagador["source"]["geolocation"] = None
        PixJourney.send(pagador)
        DbUtils.seed_sent(
            conta_id(pagador["source_account"]),
            conta_id(pagador["destination_account"]),
            count=1,
            amount=10_000,
            minutes_ago=5 * 60,
            device_id=pagador["source"]["device_id"],
            geolocation=SAO_PAULO,
        )

        em_recife = PixJourney.from_same_source(pagador)
        em_recife["source"]["geolocation"] = RECIFE
        status, reasons = PixJourney.send(em_recife)

        assert (status, reasons) == ("approved", [])

    def test_new_account_receiving_from_a_few_friends(self):
        """Conta aberta anteontem recebe de 5 amigos ao longo do dia (aqui,
        espaçados o bastante pra não ser uma rajada)."""
        primeiro = cliente()
        primeiro_amigo = PixJourney.from_same_source(primeiro)
        primeiro_amigo["destination_account"]["opening_date"] = PixJourney.days_ago(2)
        results = [PixJourney.send(primeiro_amigo)]
        for _ in range(4):
            time.sleep(1.1)
            amigo = cliente()
            pix = PixJourney.from_same_source(amigo)
            pix["destination_account"] = primeiro_amigo["destination_account"]
            results.append(PixJourney.send(pix))

        assert travados(results) == []


class TestGroupPayments:
    """Vários amigos pagando a mesma pessoa ao mesmo tempo: rachar a conta,
    vaquinha, rifa. Os amigos são clientes conhecidos (aparelho reconhecido)."""

    def amigos_pagando(self, quantidade: int, intervalo: float) -> list:
        recebedor = PixJourney.new()["destination_account"]
        amigos = [cliente() for _ in range(quantidade)]
        results = []
        for amigo in amigos:
            pix = PixJourney.from_same_source(amigo)
            pix["destination_account"] = recebedor
            results.append(PixJourney.send(pix))
            time.sleep(intervalo)
        return results

    def test_splitting_the_restaurant_bill(self):
        """Seis amigos pagam a parte deles, uns segundos um do outro."""
        results = self.amigos_pagando(6, intervalo=1.5)

        assert travados(results) == []


class TestBusinesses:
    def test_monthly_payroll(self):
        """Empresa com histórico (60 Pix por mês) paga a folha de 30
        funcionários numa tarde.

        ATRITO conhecido: o piso da rajada CNPJ pede 2FA do 21º
        funcionário em diante.
        """
        empresa = cliente(source_document_number=RandomGenerator.generate_cnpj())
        com_historico(empresa, count=60, amount=300_000, days_ago=15)

        results = [PixJourney.send(PixJourney.from_same_source(empresa, amount=300_000)) for _ in range(30)]

        assert recusados(results) == []

    def test_busy_day_at_a_shop(self):
        """Loja antiga que recebe em média R$ 2.000 por dia tem uma sexta-feira
        forte: 7 clientes pagam R$ 1.000 cada.

        ATRITO conhecido: acima de 3x a média diária, os compradores
        seguintes pedem 2FA.
        """
        primeiro = PixJourney.new(destination_document_number=RandomGenerator.generate_cnpj())
        primeiro["destination_account"]["opening_date"] = "2020-01-01T10:00:00-03:00"
        cliente(primeiro)
        loja = primeiro["destination_account"]
        DbUtils.seed_received_from_distinct_payers(conta_id(loja), 60, 100_000, minutes_ago=2 * 24 * 60)

        results = []
        for _ in range(7):
            comprador = cliente()
            pix = PixJourney.from_same_source(comprador, amount=100_000)
            pix["destination_account"] = loja
            results.append(PixJourney.send(pix))

        assert recusados(results) == []

    def test_new_shop_opening_day(self):
        """Loja aberta há uma semana tem o dia da inauguração: R$ 60 mil em
        vendas. Uma confirmação dos compradores é aceitável; recusar, não."""
        primeiro = PixJourney.new(destination_document_number=RandomGenerator.generate_cnpj())
        primeiro["destination_account"]["opening_date"] = PixJourney.days_ago(7)
        cliente(primeiro)
        loja = primeiro["destination_account"]

        results = []
        for _ in range(6):
            comprador = cliente()
            pix = PixJourney.from_same_source(comprador, amount=1_000_000)
            pix["destination_account"] = loja
            results.append(PixJourney.send(pix))

        assert recusados(results) == []
