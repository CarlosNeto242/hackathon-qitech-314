import os


SERVICE_ROOT = os.path.abspath(os.path.dirname(__file__))

# Onde moram os arquivos de schema — os .json que descrevem o formato
# que cada requisicao precisa ter. Quem le essa pasta e o
# src/utils/schema_handler.py.
SCHEMA_PATH = os.path.join(SERVICE_ROOT, "schemas")

APP_ENV = os.environ.get("APP_ENV", "local")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "bootcamp-api")

DATABASE_URL = os.environ.get("DATABASE_URL")
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN")

# O ISPB deste banco. Toda conta de ORIGEM é nossa, então o participant
# dela é sempre este valor, e o que vier no payload é ignorado. Um destino
# interno chega com este mesmo ISPB e cai na mesma linha de `account`.
# O enunciado não informa o ISPB; o padrão abaixo ainda precisa ser confirmado.
BANK_ISPB = os.environ.get("BANK_ISPB", "32402502")

# O DICT do Banco Central (na sua máquina, um mock). O endereço vem do
# ambiente: o mesmo connector fala com o mock e falaria com o real.
DICT_API_URL = os.environ.get("DICT_API_URL", "http://localhost:8081")
DICT_API_INTERNAL_TOKEN = os.environ.get("DICT_API_INTERNAL_TOKEN", "default_token")

# Em SEGUNDOS, e fracionário de propósito: o DICT está no caminho do Pix,
# que tem poucos segundos pra decidir. Passou disso, o motor segue sem ele.
DICT_API_TIMEOUT = float(os.environ.get("DICT_API_TIMEOUT", "0.3"))

# Rotas públicas: não exigem o header INTERNAL-TOKEN. São as duas que
# precisam responder pra quem ainda não tem token nenhum: a raiz, que
# diz quem é este serviço, e o health check, que o Docker consulta pra
# saber se a API já está de pé.
BYPASS_ENDPOINTS = [
    "/",
    "/health_check",
]

REQUIRED_VARIABLES = ["DATABASE_URL", "INTERNAL_TOKEN"]


def check_variables():
    missing = []
    for name in REQUIRED_VARIABLES:
        if not globals().get(name):
            missing.append(name)

    if missing:
        raise EnvironmentError(
            f"Faltam variáveis de ambiente: {', '.join(missing)}. "
            "Rodando com 'docker compose up' elas já vêm preenchidas. "
            "Fora do Docker, copie o .env.example para .env."
        )
