import http.client
import ssl

from stack import ROOT, setting

HOST = "127.0.0.1"
TIMEOUT_SECONDS = 15
CA_FILE = ROOT / "certs" / "ca.crt"


def http_port() -> int:
    return int(setting("HTTP_PORT", "21080"))


def https_port() -> int:
    return int(setting("HTTPS_PORT", "21443"))


def trusted_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(CA_FILE))


def fetch(
    path: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    secure: bool = True,
    context: ssl.SSLContext | None = None,
) -> tuple[int, dict[str, str], str]:
    if secure:
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            HOST, https_port(), timeout=TIMEOUT_SECONDS, context=context or trusted_context()
        )
    else:
        connection = http.client.HTTPConnection(HOST, http_port(), timeout=TIMEOUT_SECONDS)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            response.read().decode("utf-8", "replace"),
        )
    finally:
        connection.close()
