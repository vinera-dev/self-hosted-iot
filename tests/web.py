import http.client

from stack import setting

HOST = "127.0.0.1"
TIMEOUT_SECONDS = 15


def http_port() -> int:
    return int(setting("HTTP_PORT", "21080"))


def fetch(
    path: str, method: str = "GET", headers: dict[str, str] | None = None, body: str | None = None
) -> tuple[int, dict[str, str], str]:
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
