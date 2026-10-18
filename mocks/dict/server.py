import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARKED_DOCUMENT = "11144477735"
SLOW_DOCUMENT = "22255588846"
ERROR_DOCUMENT = "33366699957"

SLOW_SECONDS = 2

PATH_PATTERN = re.compile(r"^/dict/(\d{11}|\d{14})/statistics$")

FRAUD_TYPES = (
    "ApplicationFrauds",
    "MuleAccounts",
    "ScammerAccounts",
    "OtherFrauds",
    "UnknownFrauds",
    "TotalFraudTransactionAmount",
    "DistinctFraudReporters",
)


def counters(d90: int = 0, m12: int = 0, m60: int = 0) -> dict:
    return {"d90": d90, "m12": m12, "m60": m60}


def person_statistics(document_number: str) -> dict:
    fraud_markers = {fraud_type: counters() for fraud_type in FRAUD_TYPES}
    fraud_markers["Watermark"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    if document_number == MARKED_DOCUMENT:
        fraud_markers["MuleAccounts"] = counters(2, 3, 3)
        fraud_markers["DistinctFraudReporters"] = counters(2, 2, 2)

    return {
        "TaxIdNumber": document_number,
        "PersonStatistics": {"FraudMarkers": fraud_markers},
    }


class DictHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        match = PATH_PATTERN.match(self.path)
        if match is None:
            self._respond(404, {"error": "not found"})
            return

        document_number = match.group(1)

        if document_number == SLOW_DOCUMENT:
            time.sleep(SLOW_SECONDS)

        if document_number == ERROR_DOCUMENT:
            self._respond(500, {"error": "internal error"})
            return

        self._respond(200, person_statistics(document_number))

    def _respond(self, status: int, body: dict) -> None:
        content = json.dumps(body).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8081), DictHandler)
    print("Mock do DICT ouvindo na porta 8081", flush=True)
    server.serve_forever()
