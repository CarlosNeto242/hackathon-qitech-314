# Todos os números das regras antifraude, num lugar só (CLAUDE.md, seção 5).
#
# Cada valor diz de onde veio:
#   [TIME]     — escrito nos comentários do controller pelo time;
#   [PROPOSTA] — sugestão para revisar; troque à vontade.
#
# Valores de dinheiro em CENTAVOS, como o `amount` do payload.

# ─── DICT ─────────────────────────────────────────────────────────────

# Marcações confirmadas nos últimos 90 dias (d90) que já rejeitam. [PROPOSTA]
DICT_FRAUD_MARKERS_MIN = 1
DICT_FRAUD_TYPES = ("MuleAccounts", "ScammerAccounts", "ApplicationFrauds")

# ─── Destino CPF ──────────────────────────────────────────────────────

# Conta recém-criada: menos de 5 dias. [TIME]
DEST_CPF_NEW_ACCOUNT_DAYS = 5
# Contas pagadoras DISTINTAS desde a abertura, para conta recém-criada.
# Mais de 20 pede 2FA, mais de 50 rejeita. [TIME — lido como contas
# distintas, como na RFC, e não como número de Pix nem como valor]
DEST_CPF_NEW_ACCOUNT_PAYERS_2FA = 20
DEST_CPF_NEW_ACCOUNT_PAYERS_REJECT = 50
# Frequência de recebimento, em três janelas (rajada de 1 s, 1 min e 1 h).
# As três contam os Pix recebidos pelo DOCUMENTO (todas as contas do mesmo
# CPF), não só pela conta: o laranja com várias contas não escapa espalhando
# os recebimentos. [TIME]
#
# Mais de 10 Pix em 1 minuto rejeita.
# Substitui o intervalo de 0,2 s / 1,0 s entre recebimentos, que puniria o
# segundo de dois pagadores independentes. [PROPOSTA]
DEST_CPF_VELOCITY_WINDOW_MINUTES = 1
DEST_CPF_VELOCITY_MAX = 10
# Rajada: vários Pix por segundo. Mais de 3 no mesmo segundo (a partir do
# 4º) rejeita. Alguns pagadores independentes no mesmo segundo acontece;
# quatro já não é coincidência numa conta de pessoa física. [PROPOSTA]
DEST_CPF_BURST_WINDOW_SECONDS = 1
DEST_CPF_BURST_MAX = 3
# Janela longa: mais de 100 Pix recebidos em 1 hora rejeita. Pega o laranja
# paciente, que recebe o tempo todo sem nunca passar das janelas curtas. [TIME]
DEST_CPF_LONG_WINDOW_HOURS = 1
DEST_CPF_LONG_WINDOW_MAX = 100

# ─── Destino CNPJ ─────────────────────────────────────────────────────

# Conta recente: menos de 30 dias. [PROPOSTA — o time tinha um bloco vazio
# "se a idade da conta for menor que 30 dias"]
DEST_CNPJ_NEW_ACCOUNT_DAYS = 30
# Montante = soma recebida nas últimas 24 h, contando o Pix atual. [PROPOSTA]
DEST_CNPJ_AMOUNT_WINDOW_HOURS = 24
# Conta recente: acima de R$ 50.000 em 24 h pede 2FA. [PROPOSTA]
DEST_CNPJ_NEW_ACCOUNT_AMOUNT_LIMIT = 5_000_000
# Conta não recente: acima de 3x a média diária dos 30 dias anteriores pede
# 2FA. Precisa de pelo menos 60 recebimentos nesse período (cerca de 2 por
# dia) pra ter histórico. [PROPOSTA]
DEST_CNPJ_HISTORY_DAYS = 30
DEST_CNPJ_HISTORY_MIN_TRANSACTIONS = 60
DEST_CNPJ_ABOVE_NORMAL_FACTOR = 3
# Sem histórico: acima de R$ 200.000 em 24 h pede 2FA. [PROPOSTA]
DEST_CNPJ_NO_HISTORY_AMOUNT_LIMIT = 20_000_000

# ─── Origem: valor ────────────────────────────────────────────────────

# Só acima deste valor a regra olha o histórico: R$ 2.000 no CPF e
# R$ 100.000 no CNPJ. [TIME]
SRC_CPF_AMOUNT_LIMIT = 200_000
SRC_CNPJ_AMOUNT_LIMIT = 10_000_000
# Tem histórico: conta aberta há 60 dias ou mais E pelo menos 30 Pix
# aprovados ou com 2FA nos últimos 90 dias. Conta também os de 2FA (premissa:
# o 2FA foi cumprido); só com aprovados seria circular. [TIME; a janela de
# 90 dias é PROPOSTA]
SRC_HISTORY_MIN_ACCOUNT_AGE_DAYS = 60
SRC_HISTORY_MIN_TRANSACTIONS = 30
SRC_HISTORY_WINDOW_DAYS = 90
# Sem histórico: acima do limite pede 2FA. Com histórico: acima de 1,5x o
# percentil 95 dos Pix aprovados ou com 2FA pede 2FA. [TIME: "5% mais
# altos" e "1,5x"; trocado a média dos 5% maiores pelo p95, porque com
# poucas transações os 5% maiores são um ou dois Pix só]
SRC_AMOUNT_PERCENTILE = 0.95
SRC_AMOUNT_FACTOR = 1.5

# ─── Origem: velocidade de envio (CPF) ────────────────────────────────

# Mais de 3 Pix em 2 min pede 2FA; mais de 10 em 2 min rejeita. Substitui o
# intervalo de 0,2 s / 1,0 s, frágil com scripts e retentativas. [PROPOSTA]
SRC_CPF_VELOCITY_WINDOW_MINUTES = 2
SRC_CPF_VELOCITY_2FA = 3
SRC_CPF_VELOCITY_REJECT = 10

# ─── Origem: rajada de envios (CNPJ) ──────────────────────────────────

# Com histórico (pelo menos 60 envios nos 30 dias anteriores): envios na
# última hora acima de 6x a média por hora pede 2FA. O piso de 20 evita que
# uma média minúscula dispare com 1 Pix; na prática, empresas com menos de
# ~2.400 envios por mês ficam no piso. [PROPOSTA]
SRC_CNPJ_BURST_WINDOW_HOURS = 1
SRC_CNPJ_BURST_HISTORY_DAYS = 30
SRC_CNPJ_BURST_HISTORY_MIN_TRANSACTIONS = 60
SRC_CNPJ_BURST_FACTOR = 6
SRC_CNPJ_BURST_MIN = 20
# Sem histórico: mais de 15 envios na última hora pede 2FA. Menor que o piso
# com histórico: empresa sem histórico merece menos confiança. [PROPOSTA]
SRC_CNPJ_BURST_NO_HISTORY_MAX = 15

# ─── Origem: teleporte ────────────────────────────────────────────────

# Acima de 900 km/h (velocidade de avião comercial) com pelo menos 50 km
# de distância (abaixo disso é ruído de GPS) rejeita. [PROPOSTA]
TELEPORT_MAX_SPEED_KMH = 900
TELEPORT_MIN_DISTANCE_KM = 50

# ─── Reincidência ─────────────────────────────────────────────────────

# Olha os últimos 30 Pix da conta no mesmo papel, desde o último desbloqueio
# e dentro de 30 dias. Mais de 8 rejeições por risco bloqueia o destino;
# a origem, cliente do banco, exige mais evidência: mais de 10. [PROPOSTA]
REINCIDENCE_LAST_TRANSACTIONS = 30
REINCIDENCE_WINDOW_DAYS = 30
REINCIDENCE_DEST_MAX_REJECTIONS = 8
REINCIDENCE_SRC_MAX_REJECTIONS = 10
