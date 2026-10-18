# O motor antifraude: recebe um Pix, decide e grava. O fluxo de decisão está
# descrito no CLAUDE.md (seção 4); todos os números moram em src/parameters.py.

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.exc import IntegrityError

import parameters as p
from connectors import DictConnector, DictUnavailable
from constants import BANK_ISPB
from controllers.base_controller import BaseController
from dtos import PixTransactionDTO
from errors import (
    AccountDataMismatch,
    InvalidDateTime,
    InvalidPixDocumentNumber,
    NotFoundPixTransaction,
    PixIdConflict,
)
from models import Account, AccountEvent, PixTransaction
from repositories import AccountRepository, PixTransactionRepository
from utils.document_number import CPF_LENGTH, is_valid_document, only_digits

PIX_ID_UNIQUE_CONSTRAINT = "transaction_pix_id_key"

DESTINATION = "destination"
SOURCE = "source"

# Um sinal é (decisão, motivo). A decisão final é a mais grave entre eles.
Signal = Tuple[str, str]

SEVERITY = {
    PixTransaction.APPROVED: 0,
    PixTransaction.TWO_FACTOR_REQUIRED: 1,
    PixTransaction.REJECTED: 2,
}

EARTH_RADIUS_KM = 6371


class PixTransactionController(BaseController):

    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)
        self.pix_transaction_repository = PixTransactionRepository(self.context)
        self.dict_connector = DictConnector()

    def analyze(self, payload: dict) -> Tuple[dict, bool]:

        pix_id = payload["id"]
        payload_hash = self._fingerprint(payload)

        existing = self.pix_transaction_repository.get_by_pix_id(pix_id)
        if existing is not None:
            return self._recorded_analysis(existing, payload_hash), False

        transaction_date = self._parse_datetime(payload["transaction_date"], "transaction_date")
        source_account_data = self._account_data(payload["source_account"], "source_account", BANK_ISPB)
        destination_account_data = self._account_data(
            payload["destination_account"],
            "destination_account",
            payload["destination_account"]["participant"],
        )

        source_account = self._register_account(source_account_data, "source_account")
        destination_account = self._register_account(destination_account_data, "destination_account")

        geolocation = payload["source"].get("geolocation") or {}
        transaction_data = {
            "pix_id": pix_id,
            "payload_hash": payload_hash,
            "amount": payload["amount"],
            "transaction_date": transaction_date,
            "source_account_id": source_account.id,
            "destination_account_id": destination_account.id,
            "device_id": payload["source"]["device_id"],
            "channel": payload["source"]["channel"],
            "ip": payload["source"]["ip"],
            "latitude": geolocation.get("latitude"),
            "longitude": geolocation.get("longitude"),
        }

        # Trava as duas contas até o commit. Sem isso, Pix simultâneos para a
        # mesma conta não se enxergam (nenhum gravou ainda) e as contagens de
        # velocidade dariam zero justamente na rajada de vários Pix por
        # segundo. Só serializa Pix da MESMA conta; contas diferentes seguem
        # em paralelo.
        self.account_repository.lock_accounts([source_account.id, destination_account.id])
        # Destino CPF conta os recebimentos pelo documento (todas as contas do
        # CPF), então a fila também precisa ser pelo documento.
        if len(destination_account.document_number) == CPF_LENGTH:
            self.account_repository.lock_document(destination_account.document_number)

        status, decision_reasons, rejected_by = self._decide(source_account, destination_account, transaction_data)

        pix_transaction = self.pix_transaction_repository.create(transaction_data, status, decision_reasons)

        try:
            # O flush grava a transação antes do commit, pra que ela
            # já tenha id (o evento de bloqueio aponta pra ela) e pra que a
            # contagem da reincidência já a inclua. A corrida do pix_id passa
            # a estourar aqui, por isso o flush está dentro do try.
            self.session.flush()

            if rejected_by == DESTINATION:
                self._apply_reincidence(destination_account, DESTINATION, pix_transaction)
            elif rejected_by == SOURCE:
                self._apply_reincidence(source_account, SOURCE, pix_transaction)

            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            if self._constraint_name(error) != PIX_ID_UNIQUE_CONSTRAINT:
                raise

            existing = self.pix_transaction_repository.get_by_pix_id(pix_id)
            return self._recorded_analysis(existing, payload_hash), False

        return PixTransactionDTO.obj_to_dict(pix_transaction), True

    def _recorded_analysis(self, existing: PixTransaction, payload_hash: str) -> dict:
        """Idempotência: o mesmo Pix de novo devolve a análise gravada. O mesmo
        id com OUTRO conteúdo é conflito, nunca a análise de outra transação."""
        if existing.payload_hash != payload_hash:
            self.logger.warning(f"pix_id {existing.pix_id} reenviado com outro conteudo")
            raise PixIdConflict(existing.pix_id)

        return PixTransactionDTO.obj_to_dict(existing)

    def _fingerprint(self, payload: dict) -> str:
        """SHA-256 do payload em forma canônica (chaves em ordem, sem espaços).
        Um reenvio idêntico gera o mesmo hash; qualquer campo diferente, outro."""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get_by_pix_id(self, pix_id: str) -> dict:
        pix_transaction = self.pix_transaction_repository.get_by_pix_id(pix_id)
        if pix_transaction is None:
            raise NotFoundPixTransaction(pix_id)

        return PixTransactionDTO.obj_to_dict(pix_transaction)

    # ─── Decisão ──────────────────────────────────────────────────────────

    def _decide(
        self, source_account: Account, destination_account: Account, pix: dict
    ) -> Tuple[str, List[str], Optional[str]]:
        """Devolve (status, motivos, papel que rejeitou ou None).

        Cada regra acrescenta um sinal (decisão, motivo) em `signals`. No fim,
        vale a decisão mais grave (ver _combine).
        """

        if Account.PROHIBITED in (source_account.status, destination_account.status):
            return PixTransaction.REJECTED, [PixTransaction.ACCOUNT_BLOCKED], None

        now = datetime.now(timezone.utc)
        repository = self.pix_transaction_repository
        signals: List[Signal] = []

        # ═══ VERIFICAÇÃO DO DESTINO ═══════════════════════════════════════

        destination = destination_account
        destination_age = now - destination.opening_date

        # Consulta o DICT pelo documento; marcação de fraude já rejeita.
        if self._dict_fraud_marked(destination.document_number):
            return PixTransaction.REJECTED, [PixTransaction.DEST_FRAUD_MARKED], DESTINATION

        if len(destination.document_number) == CPF_LENGTH:
            # ─── CASE CPF ───

            # Conta recém-criada recebendo de muitas contas distintas.
            # Conta contas pagadoras DISTINTAS (como na RFC), contando a deste Pix.
            if destination_age < timedelta(days=p.DEST_CPF_NEW_ACCOUNT_DAYS):
                payers = repository.count_distinct_payers(destination.id, source_account.id) + 1

                if payers > p.DEST_CPF_NEW_ACCOUNT_PAYERS_REJECT:
                    signals.append((PixTransaction.REJECTED, PixTransaction.DEST_NEW_ACCOUNT))
                elif payers > p.DEST_CPF_NEW_ACCOUNT_PAYERS_2FA:
                    signals.append((PixTransaction.TWO_FACTOR_REQUIRED, PixTransaction.DEST_NEW_ACCOUNT))

            # Frequência de recebimento, em três janelas: vários Pix no mesmo
            # segundo (rajada), muitos no mesmo minuto e muitos na mesma hora
            # (o laranja paciente). Contadas pelo DOCUMENTO: o laranja com
            # várias contas não escapa espalhando os recebimentos.
            # Contagem numa janela, e não o intervalo entre dois recebimentos:
            # o intervalo depende de pagadores independentes (puniria o segundo
            # de dois pagadores legítimos).
            windows = (
                (timedelta(seconds=p.DEST_CPF_BURST_WINDOW_SECONDS), p.DEST_CPF_BURST_MAX),
                (timedelta(minutes=p.DEST_CPF_VELOCITY_WINDOW_MINUTES), p.DEST_CPF_VELOCITY_MAX),
                (timedelta(hours=p.DEST_CPF_LONG_WINDOW_HOURS), p.DEST_CPF_LONG_WINDOW_MAX),
            )
            for window, maximum in windows:
                received = repository.count_received_by_document_since(destination.document_number, now - window) + 1
                if received > maximum:
                    signals.append((PixTransaction.REJECTED, PixTransaction.DEST_RECEIVING_VELOCITY))
                    break

        else:
            # ─── CASE CNPJ ───
            # Montante = soma recebida nas últimas 24 h, contando este Pix.
            window_start = now - timedelta(hours=p.DEST_CNPJ_AMOUNT_WINDOW_HOURS)
            window_sum = repository.sum_received_between(destination.id, window_start, now) + pix["amount"]

            if destination_age < timedelta(days=p.DEST_CNPJ_NEW_ACCOUNT_DAYS):
                # Conta recente com alto montante.
                limit = p.DEST_CNPJ_NEW_ACCOUNT_AMOUNT_LIMIT
            else:
                # Conta não recente com montante acima do normal: compara com a
                # média diária dos 30 dias anteriores. Sem histórico, limite fixo.
                history_start = window_start - timedelta(days=p.DEST_CNPJ_HISTORY_DAYS)
                history_count = repository.count_received_between(destination.id, history_start, window_start)

                if history_count >= p.DEST_CNPJ_HISTORY_MIN_TRANSACTIONS:
                    history_sum = repository.sum_received_between(destination.id, history_start, window_start)
                    limit = p.DEST_CNPJ_ABOVE_NORMAL_FACTOR * history_sum / p.DEST_CNPJ_HISTORY_DAYS
                else:
                    limit = p.DEST_CNPJ_NO_HISTORY_AMOUNT_LIMIT

            if window_sum > limit:
                signals.append((PixTransaction.TWO_FACTOR_REQUIRED, PixTransaction.DEST_HIGH_AMOUNT))

        # Rejeição no destino encerra o fluxo; 2FA no destino segue pra origem.
        if any(decision == PixTransaction.REJECTED for decision, _reason in signals):
            status, reasons = self._combine(signals)
            return status, reasons, DESTINATION

        # ═══ VERIFICAÇÃO DA ORIGEM ════════════════════════════════════════

        source = source_account
        source_is_cpf = len(source.document_number) == CPF_LENGTH

        # ─── Valor: só acima do limite olha o histórico ───
        # Limites em CENTAVOS, como o amount.
        amount_limit = p.SRC_CPF_AMOUNT_LIMIT if source_is_cpf else p.SRC_CNPJ_AMOUNT_LIMIT

        if pix["amount"] > amount_limit:
            history_since = now - timedelta(days=p.SRC_HISTORY_WINDOW_DAYS)
            old_enough = now - source.opening_date >= timedelta(days=p.SRC_HISTORY_MIN_ACCOUNT_AGE_DAYS)
            # Conta aprovados E 2FA, com a mesma premissa do aparelho reconhecido
            # (o 2FA foi cumprido). Só com aprovados seria circular: um cliente
            # cujos Pix grandes sempre pedem 2FA nunca formaria histórico.
            accepted = repository.count_accepted_sent_since(source.id, history_since)

            if not old_enough or accepted < p.SRC_HISTORY_MIN_TRANSACTIONS:
                # Sem histórico → 2FA.
                signals.append((PixTransaction.TWO_FACTOR_REQUIRED, PixTransaction.SRC_HIGH_AMOUNT))
            else:
                # Com histórico → acima de 1,5x o percentil 95 → 2FA.
                # Percentil 95, e não a média dos 5% mais altos: com poucas
                # transações, os 5% mais altos são um ou dois Pix só.
                p95 = repository.accepted_sent_amount_percentile(source.id, history_since, p.SRC_AMOUNT_PERCENTILE)
                if pix["amount"] > p.SRC_AMOUNT_FACTOR * p95:
                    signals.append((PixTransaction.TWO_FACTOR_REQUIRED, PixTransaction.SRC_HIGH_AMOUNT))

        # ─── Velocidade de envio ───
        if source_is_cpf:
            # Contagem numa janela, e não o intervalo entre dois envios (mais
            # robusta a script e retentativa).
            since = now - timedelta(minutes=p.SRC_CPF_VELOCITY_WINDOW_MINUTES)
            sent = repository.count_sent_between(source.id, since, now) + 1

            if sent > p.SRC_CPF_VELOCITY_REJECT:
                signals.append((PixTransaction.REJECTED, PixTransaction.SRC_SENDING_VELOCITY))
            elif sent > p.SRC_CPF_VELOCITY_2FA:
                signals.append((PixTransaction.TWO_FACTOR_REQUIRED, PixTransaction.SRC_SENDING_VELOCITY))
        else:
            # Rajada relativa ao histórico, com piso pra média minúscula não
            # disparar com 1 Pix.
            window_start = now - timedelta(hours=p.SRC_CNPJ_BURST_WINDOW_HOURS)
            sent = repository.count_sent_between(source.id, window_start, now) + 1

            history_start = window_start - timedelta(days=p.SRC_CNPJ_BURST_HISTORY_DAYS)
            history = repository.count_sent_between(source.id, history_start, window_start)

            if history >= p.SRC_CNPJ_BURST_HISTORY_MIN_TRANSACTIONS:
                windows_in_history = p.SRC_CNPJ_BURST_HISTORY_DAYS * 24 / p.SRC_CNPJ_BURST_WINDOW_HOURS
                limit = max(p.SRC_CNPJ_BURST_FACTOR * history / windows_in_history, p.SRC_CNPJ_BURST_MIN)
            else:
                limit = p.SRC_CNPJ_BURST_NO_HISTORY_MAX

            if sent > limit:
                signals.append((PixTransaction.TWO_FACTOR_REQUIRED, PixTransaction.SRC_SENDING_VELOCITY))

        # ─── Dispositivo nunca usado antes na conta (Pix aprovado ou com 2FA) ───
        if not repository.device_recognized(source.id, pix["device_id"]):
            signals.append((PixTransaction.TWO_FACTOR_REQUIRED, PixTransaction.SRC_NEW_DEVICE))

        # ─── Localização muda drasticamente em pouco tempo ───
        # No CNPJ, só compara com o mesmo dispositivo (empresa tem operadores
        # em lugares diferentes). Sem localização, neste Pix ou no anterior,
        # a regra não dispara.
        if pix["latitude"] is not None:
            device_filter = None if source_is_cpf else pix["device_id"]
            last = repository.last_located_sent(source.id, device_filter)

            if last is not None:
                distance_km = self._haversine_km(last.latitude, last.longitude, pix["latitude"], pix["longitude"])
                hours = (now - last.created_at).total_seconds() / 3600

                if distance_km >= p.TELEPORT_MIN_DISTANCE_KM and (
                    hours <= 0 or distance_km / hours > p.TELEPORT_MAX_SPEED_KMH
                ):
                    signals.append((PixTransaction.REJECTED, PixTransaction.SRC_LOCATION_MISMATCH))

        status, reasons = self._combine(signals)
        rejected_by = SOURCE if status == PixTransaction.REJECTED else None
        return status, reasons, rejected_by

    # ─── DICT ─────────────────────────────────────────────────────────────

    def _dict_fraud_marked(self, document_number: str) -> bool:
        """Soma das marcações d90. DICT fora do ar ou resposta fora do formato
        esperado → segue sem ele (False), com aviso no log.

        Ler o formato da resposta poderia morar no connector; está aqui junto
        da regra que usa os contadores.
        """
        try:
            response = self.dict_connector.get_person_statistics(document_number)
        except DictUnavailable:
            return False

        if response.status != 200:
            self.logger.warning(f"DICT respondeu {response.status}; seguindo sem ele")
            return False

        try:
            markers = response.json["PersonStatistics"]["FraudMarkers"]
            total = sum(int(markers[fraud_type]["d90"]) for fraud_type in p.DICT_FRAUD_TYPES)
        except (TypeError, KeyError, ValueError):
            self.logger.warning("DICT respondeu fora do formato esperado; seguindo sem ele")
            return False

        return total >= p.DICT_FRAUD_MARKERS_MIN

    # ─── Reincidência ─────────────────────────────────────────────────────

    def _apply_reincidence(self, account: Account, role: str, pix_transaction: PixTransaction) -> None:
        """Conta as rejeições por risco nos últimos Pix da conta, no mesmo papel,
        desde o último desbloqueio. Passou do limite → bloqueia e grava o evento.

        A janela de 30 dias impede que rejeições antigas se acumulem. A origem
        tem limite mais alto que o destino. A transação atual já foi gravada
        pelo flush, então entra na contagem.
        """
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=p.REINCIDENCE_WINDOW_DAYS)

        last_unblock = self.account_repository.last_unblock_at(account.id)
        if last_unblock is not None and last_unblock > since:
            since = last_unblock

        if role == DESTINATION:
            recent = self.pix_transaction_repository.last_transactions_as_destination(
                account.id, since, p.REINCIDENCE_LAST_TRANSACTIONS
            )
            max_rejections = p.REINCIDENCE_DEST_MAX_REJECTIONS
            reason = AccountEvent.REPEATED_RISK_REJECTIONS_DEST
        else:
            recent = self.pix_transaction_repository.last_transactions_as_source(
                account.id, since, p.REINCIDENCE_LAST_TRANSACTIONS
            )
            max_rejections = p.REINCIDENCE_SRC_MAX_REJECTIONS
            reason = AccountEvent.REPEATED_RISK_REJECTIONS_SRC

        rejections = 0
        for transaction in recent:
            if (
                transaction.status == PixTransaction.REJECTED
                and PixTransaction.ACCOUNT_BLOCKED not in transaction.decision_reasons
            ):
                rejections += 1

        if rejections <= max_rejections:
            return

        # Trava a linha antes de mudar, pra dois Pix simultâneos não gravarem
        # dois eventos de bloqueio.
        locked = self.account_repository.get_by_id_for_update(account.id)
        if locked.status == Account.PERMITTED:
            self.account_repository.update_status(locked, Account.PROHIBITED, reason, pix_transaction.id)
            self.logger.info(f"Conta {account.id} bloqueada por reincidencia ({role}): {rejections} rejeicoes")

    # ─── Auxiliares ───────────────────────────────────────────────────────

    def _combine(self, signals: List[Signal]) -> Tuple[str, List[str]]:
        """Decisão mais grave; motivos de rejeição primeiro, depois os de 2FA,
        cada grupo na ordem em que as regras rodaram, sem repetir."""
        if not signals:
            return PixTransaction.APPROVED, []

        status = max((decision for decision, _reason in signals), key=lambda decision: SEVERITY[decision])

        reasons = []
        for decision in (PixTransaction.REJECTED, PixTransaction.TWO_FACTOR_REQUIRED):
            for signal_decision, reason in signals:
                if signal_decision == decision and reason not in reasons:
                    reasons.append(reason)

        return status, reasons

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

    # ─── Validação e registro de contas (igual ao controller atual) ──────

    def _register_account(self, account_data: dict, field: str) -> Account:

        account = self.account_repository.get_or_create(account_data)

        divergent_fields = []
        if account.document_number != account_data["document_number"]:
            divergent_fields.append("document_number")
        if account.opening_date != account_data["opening_date"]:
            divergent_fields.append("opening_date")

        if divergent_fields:
            self.logger.warning(
                f"Divergencia de dados em {field} (account.id={account.id}): {', '.join(divergent_fields)}"
            )
            raise AccountDataMismatch()

        return account

    def _account_data(self, raw_account: dict, field: str, participant: str) -> dict:

        document_number = raw_account["owner"]["document_number"]
        if not is_valid_document(document_number):
            raise InvalidPixDocumentNumber(f"{field}.owner.document_number")

        return {
            "participant": participant,
            "branch": raw_account["branch"],
            "account_number": raw_account["account_number"],
            "opening_date": self._parse_datetime(raw_account["opening_date"], f"{field}.opening_date"),
            "document_number": only_digits(document_number),
        }

    def _parse_datetime(self, raw_value: str, field: str) -> datetime:
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            raise InvalidDateTime(field)

    def _constraint_name(self, error: IntegrityError) -> Optional[str]:
        diag = getattr(error.orig, "diag", None)
        return getattr(diag, "constraint_name", None)
