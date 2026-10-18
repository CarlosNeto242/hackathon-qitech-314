# CLAUDE.md: Antifraude Pix (Hackathon QI Tech 2026)

Contexto do projeto para o time e para o Claude Code. Leia tudo antes de escrever código.
Itens marcados **A DEFINIR** não devem ser inventados: proponha com justificativa e espere a decisão do time.

## 1. Visão geral

Hackathon do Bootcamp QI Tech 2026 (Risk Solutions). O time constrói o **motor antifraude de Pix**: uma API que recebe
uma transação Pix, aplica regras de antifraude e devolve uma decisão antes do dinheiro sair.

- **Decisões possíveis:** `approved`, `rejected`, `two_factor_required`.
- **Princípios do enunciado:** decisão em poucos segundos; as regras comparam com o histórico de pagador e destino;
  bloquear cliente bom também é prejuízo; toda decisão sai com motivo explicável.
- **Base:** este repositório é o **Base Service** da QI Tech. Seguir os padrões dele (ver seção 9).
- **Idioma:** respostas, documentação e README em português do Brasil. Nomes de código (variáveis, tabelas, enums) em inglês.

### Prazos

| Evento | Quando |
|---|---|
| Entrega do link do repositório | Domingo, 18/10, até 12:00, no grupo da final no Slack |
| Apresentações | Domingo, 18/10, 13:00 a 15:00 (7 min + 3 min de perguntas) |

### Critérios de avaliação

1. Profundidade antifraude. 2. Padrão de código (Base Service, camadas, testes). 3. Modelagem de dados.
4. Solução funcional: roda seguindo o README, **cada Pix recebido fica gravado e consultável**, decisões batem com as regras.
5. Documentação (a correção começa pelo README). 6. Apresentação.

### Escopo

Entra: `POST` e `GET` do Pix, banco próprio com histórico, regras e testes, README, rota administrativa de desbloqueio.
Fica de fora: onboarding/cadastro de contas, front-end, outras APIs.

## 2. Contrato da API

### `POST /pix/transaction`

```json
{
  "id": "pix-000123",
  "amount": 150000,
  "transaction_date": "2026-10-17T22:15:00-03:00",
  "source_account": {
    "branch": "0001",
    "account_number": "88213",
    "opening_date": "2025-03-02T10:00:00-03:00",
    "owner": { "document_number": "123.456.789-09" }
  },
  "destination_account": {
    "participant": "60701190",
    "branch": "3675",
    "account_number": "10442",
    "opening_date": "2026-10-10T09:00:00-03:00",
    "owner": { "document_number": "987.654.321-00" }
  },
  "source": {
    "device_id": "dvc-9f2c71a8",
    "channel": "app",
    "ip": "198.51.100.23",
    "geolocation": { "latitude": -23.56, "longitude": -46.65 }
  }
}
```

`amount` em centavos. `geolocation` é opcional. `channel` é texto livre.

Resposta:

```json
{ "key": "b3f1c2e0-...", "status": "two_factor_required", "metadata": { "reasons": ["SRC_NEW_DEVICE"] } }
```

`metadata` é `{}` quando aprovado e `{"reasons": [...]}` caso contrário.

### Rotas

Todas exigem o header `INTERNAL-TOKEN` (padrão do Base Service), menos `/` e `/health_check`.

| Rota | Método | Respostas |
|---|---|---|
| `/pix/transaction` | POST | **201** análise nova; **200** se o `pix_id` já existia com o mesmo conteúdo (devolve a análise gravada); **409** se o `pix_id` já existia com outro conteúdo; 400 payload inválido (schema, inclusive IP inválido); 422 valor impossível (data, dígito de CPF/CNPJ) ou divergência de dados da conta; 403 sem token |
| `/pix/transaction/{pix_id}` | GET | 200 com a análise gravada (sem reanalisar); 404 se não existir |
| `/admin/accounts/unblock` | POST | Corpo `{participant, branch, account_number}` (origem: `participant` = `BANK_ISPB`). 200 com os três campos e o `status`; 400 corpo inválido; 403 sem token; 404 conta inexistente; 409 conta já `PERMITTED` |

- A decisão antifraude vai **no corpo**. `rejected` é uma análise bem-sucedida e responde 201/200, nunca 4xx.
- POST e GET usam **a mesma função** (DTO) para montar a resposta.

## 3. Modelo de dados

Tabelas: `account`, `transaction`, `events`. Definição exata em `database/database.sql`.

- **`account`**: `participant`, `branch`, `account_number`, `opening_date` (timestamptz), `document_number` (só dígitos,
  11 = CPF, 14 = CNPJ), `status` (`account_status`). `UNIQUE (participant, branch, account_number)`.
- **`transaction`**: `pix_id` (UNIQUE, até 16 caracteres), `payload_hash` (SHA-256 do payload recebido), `transaction_key` (uuid, sai como `key`), `amount`
  (bigint, centavos), `transaction_date` (do payload), `created_at` (do servidor), contas de origem e destino,
  `device_id`, `channel`, `ip` (inet), `latitude`/`longitude` (opcionais), `status` (`transaction_status`) e
  **`decision_reasons decision_reason[]`** (todos os motivos que dispararam; vazio quando aprovado).
- O único CHECK do banco em `transaction` é "aprovado ⇔ sem motivos". Valor positivo, faixa e presença conjunta de
  latitude/longitude e formato do documento são garantidos pelo JSON Schema na entrada, não pelo banco.
- **`events`**: transições de estado da conta: `account_id`, `transaction_id` (nulo no desbloqueio), `from_status`,
  `to_status`, `reason` (`account_event_reason`), `created_at`.

### ENUMs (nativos do Postgres)

- `account_status`: `PERMITTED`, `PROHIBITED`.
- `transaction_status`: `approved`, `rejected`, `two_factor_required`.
- `decision_reason`:

| Valor | Regra |
|---|---|
| `ACCOUNT_BLOCKED` | Origem ou destino já estava `PROHIBITED` |
| `DEST_FRAUD_MARKED` | DICT (mock) apontou marcação de fraude no destino |
| `DEST_RECEIVING_VELOCITY` | Frequência de recebimento do destino (CPF) |
| `DEST_NEW_ACCOUNT` | Destino recém-criado com muitos pagadores distintos (CPF) |
| `DEST_HIGH_AMOUNT` | Montante recebido pelo destino numa janela (CNPJ) |
| `SRC_HIGH_AMOUNT` | Valor da origem acima da métrica do histórico ou do limite fixo |
| `SRC_SENDING_VELOCITY` | Velocidade de envio (CPF) e rajada relativa ao histórico (CNPJ) |
| `SRC_NEW_DEVICE` | Aparelho nunca reconhecido para a conta |
| `SRC_LOCATION_MISMATCH` | Teleporte (velocidade impossível entre duas localizações) |

- `account_event_reason`: `REPEATED_RISK_REJECTIONS_DEST`, `REPEATED_RISK_REJECTIONS_SRC`, `MANUAL_UNBLOCK`.

### Regras de comportamento do banco

- **Idempotência:** `pix_id` é único. Pix repetido com o mesmo conteúdo (mesmo `payload_hash`) devolve a análise
  gravada (200); com outro conteúdo é conflito (409, `QIT001014`), nunca a análise de outra transação. A violação de unicidade em corrida
  é tratada como "já existe", nunca como 500.
- **Conta nova:** `INSERT ... ON CONFLICT DO NOTHING`. Nunca sobrescreve `opening_date` nem `document_number`.
- **Participant da origem:** sempre a constante `BANK_ISPB` (padrão `32402502`, **a confirmar**), ignorando o payload.
- **Bloqueio** (permanente) e **desbloqueio** (manual): atualizam `account.status` e inserem em `events` na mesma
  transação de banco.
- **Toda transação analisada é gravada**, inclusive as rejeitadas. Payload inválido (400/422) não é transação e não grava.
- **Janelas de tempo** usam `created_at` (servidor), nunca `transaction_date` (cliente).

## 4. Fluxo de decisão

```
0) Idempotência: pix_id já existe → devolve a análise gravada (200). Fim.
1) Validação do payload (400 schema, inclusive IP; 422 data/dígito de CPF/CNPJ). Normaliza documentos (só dígitos).
   1.1) Conta já existe → compara document_number e opening_date (normalizados: dígitos e instante).
        Divergência → 422 com mensagem genérica, nada é gravado, aviso no log. (Origem e destino.)
   1.2) Conta nova → registra (ON CONFLICT DO NOTHING).
   1.3) Origem ou destino PROHIBITED → rejected [ACCOUNT_BLOCKED], sem rodar regra nenhuma.
2) Destino:
   2.1) DICT (mock) roda primeiro: consulta por pessoa (documento do destino) e soma, na janela d90,
        MuleAccounts + ScammerAccounts + ApplicationFrauds; soma ≥ 1 (proposta) → rejected.
        Timeout curto; se falhar, segue sem ele.
   2.2) CPF: contas distintas que transferiram para ela + conta recém-criada → rejected ou 2FA, conforme a
        intensidade; frequência de recebimento em três janelas (1 s, 1 min e 1 h), contada pelo DOCUMENTO
        (todas as contas do CPF) → rejected.
   2.3) CNPJ: conta recente com alto montante → 2FA; conta não recente com montante acima do normal → 2FA.
        Montante = soma recebida numa janela de tempo; sem histórico → limite fixo.
   Rejeição no destino encerra o fluxo e dispara a reincidência do destino.
   2FA no destino NÃO encerra: a origem é avaliada e vale a decisão mais grave.
3) Origem:
   3.1) CPF: valor (com histórico → métrica; sem histórico → limite fixo) → 2FA; velocidade de envio alta → 2FA,
        muito alta → rejected; aparelho novo → 2FA; teleporte (comparado ao último Pix com localização da conta) → rejected.
   3.2) CNPJ: montante acima do normal (métrica ou limite fixo) → 2FA; rajada de envios relativa ao histórico → 2FA;
        aparelho novo → 2FA; teleporte comparado ao último Pix do mesmo device_id → rejected.
   Rejeição na origem dispara a reincidência da origem.
4) Nenhum sinal → approved.
5) Grava transação, status, decision_reasons e (se houver) evento de bloqueio numa única transação de banco.
```

### Regras de combinação

- Decisão final = a mais grave entre as regras que dispararam (`rejected` > `two_factor_required` > `approved`).
- **Sinais não se somam:** vários sinais de 2FA continuam dando 2FA.
- `decision_reasons` guarda **todos** os motivos: primeiro os de rejeição, depois os de 2FA, cada grupo na ordem do fluxo.
- **Aparelho reconhecido** = `device_id` já usado pela conta em Pix `approved` ou `two_factor_required`
  (premissa: o 2FA foi cumprido; o motor não recebe o resultado). O primeiro Pix de toda conta pede 2FA.
- Contagens são por **conta**, com uma exceção: a frequência de recebimento do destino CPF (janelas de 1 s, 1 min
  e 1 h) soma todas as contas do mesmo documento, e a análise trava o documento (advisory lock) para que Pix
  simultâneos para contas diferentes do mesmo CPF se enxerguem.

### Reincidência (bloqueio automático)

- Ao rejeitar, conta as rejeições recentes da conta no mesmo papel (destino ou origem). Passando do limite, a conta
  vira `PROHIBITED` e um evento é gravado.
- Conta só `status = 'rejected'` sem `ACCOUNT_BLOCKED` e só depois do último desbloqueio da conta.
- Valores `x`, `y` e janela, separados para destino e origem: **A DEFINIR**. A origem exige mais evidência.

## 5. Parâmetros

Todos os números das regras ficam em `src/parameters.py`, cada um marcado como [TIME] ou [PROPOSTA], com o porquê.
README e código devem ter os mesmos valores.

## 6. Decisões tomadas (e o porquê)

- Destino pode pedir 2FA: funciona como confirmação extra ao pagador sobre um recebedor arriscado.
- DICT antes das regras locais do destino (mock, com timeout e fallback).
- DICT: consulta por pessoa (`GET /dict/{document_number}/statistics`, caminho simplificado em relação ao oficial
  `/api/v2/persons/{TaxIdNumber}/statistics`), porque o payload não traz chave Pix; mesma
  consulta e mesma regra para CPF e CNPJ. Só a janela `d90` (inclui o mês atual, onde está o risco de conta laranja
  recente; `m12` exclui o mês corrente). Só marcações confirmadas (laranja, golpista, fraude de cadastro); ficam de
  fora `OtherFrauds`, `UnknownFrauds` (inválido na API v2) e as notificações de infração (não confirmadas).
- Divergência de dados é dado inválido (422), não regra de negócio.
- Sem comparação IP × geolocalização (exigiria base GeoIP; imprecisa no Brasil).
- Sem redução de risco por destino já conhecido.
- Frequência relativa do destino CNPJ: fora por enquanto.

## 7. Limitações para o README

- Sem porte, CNAE nem MEI do CNPJ (MEI se comporta como CPF mas recebe limites de CNPJ).
- Visão parcial do destino: só os Pix que saem deste banco.
- `device_id` e geolocalização são autodeclarados pelo app; a defesa contra clonagem é vínculo criptográfico do aparelho.
- Divergência de dados no destino: o primeiro payload define o cadastro (risco de envenenamento; em produção o dado
  viria do DICT). Divergências não ficam no histórico nem contam para a reincidência.
- O motor não recebe o resultado do 2FA.
- Contagem por conta nas demais regras (pagadores de conta nova, montante do CNPJ, regras da origem) e bloqueio
  por conta: o laranja bloqueado que abre outra conta com o mesmo CPF volta a receber.
- Bloqueio permanente com desbloqueio manual, sem registro de operador nem justificativa.

## 8. Pontos A DEFINIR

- Todos os parâmetros numéricos (limites, janelas, métricas) e a justificativa de cada um.
- Intensidade do destino CPF recém-criado (fronteira entre 2FA e rejeição).
- `x`, `y` e janela da reincidência, para destino e origem.
- Confirmar o ISPB `32402502`.

## 9. Padrões do Base Service

- Caminho: `middlewares → resources → controllers → repositories → models`; resposta via `dtos/`.
- `resources/`: valida com `@SchemaHandler.validate("x.json")` (JSON Schema em `src/schemas/`), chama **um**
  controller, sem `raise`.
- `controllers/`: herdam de `BaseController`, decidem regra, fazem o `commit()`. Só eles chamam `get_context()`.
- `repositories/`: só consultas. `errors/custom_errors.py`: cada erro com código `QIT` único.
- Banco: `database/database.sql` roda só quando o banco nasce (`docker compose down -v` para recriar).
- Testes de integração por HTTP contra a API no Docker (`tests/integration/`); `DbUtils.rollback()` zera o banco.
- Todos os testes passam pelas rotas (`RequestGenerator`/`PixJourney`), inclusive bloqueio (gerando rejeições até a
  reincidência) e desbloqueio. `DbUtils` só onde é estritamente necessário: `rollback()` (do Base Service) e
  `seed_*`, que plantam histórico antigo (perfil de valor, média do CNPJ, pagadores de conta nova, janela de 1 h).
- Mock do DICT: serviço `dict-mock` do compose (`mocks/dict/server.py`). Documentos fixos: 11144477735 marcado,
  22255588846 lento, 33366699957 responde 500; os demais sem marcação.

## 10. Prioridades

1. POST/GET com banco e idempotência. 2. Orquestrador e regras com testes. 3. Bloqueio e desbloqueio.
4. README. 5. Refinamentos (DICT mock, regras extras).

## 11. Desempenho (para o README)

Medido em 18/10/2026, na suíte completa (802 `POST /pix/transaction`), com a API e o banco no Docker local.

| Rota | Mediana | p95 | p99 | Máximo |
|---|---|---|---|---|
| `POST /pix/transaction` | 24,5 ms | 118 ms | 266 ms | 335 ms |
| `GET /pix/transaction/{id}` | 2,5 ms | 8,5 ms | 8,5 ms | 8,5 ms |
| `POST /admin/accounts/unblock` | 3,7 ms | 24 ms | 24 ms | 24 ms |

- Um Pix típico é decidido em ~25 ms; o pior caso ficou em ~1/3 de segundo, dentro de "poucos segundos".
- Acima de 300 ms, só dois casos, ambos esperados: (1) o DICT lento: o motor desiste no timeout de 300 ms e segue sem
  ele; (2) Pix simultâneos para a MESMA conta esperando a trava da conta (análise um por vez por conta, ~25 ms cada,
  pela proteção contra rajada). Contas diferentes não esperam umas pelas outras.
- Suíte de testes: ~12 s. O único teste acima de 1 s é a janela de 1 minuto do destino (~3,9 s), que espaça
  os Pix de propósito pra testar a janela de 1 minuto sem disparar a de 1 segundo.
- Como medir de novo: `pytest --durations=15` para os testes; para a API, as linhas `SAIU ... - X ms` do log
  (`docker compose logs api`).
