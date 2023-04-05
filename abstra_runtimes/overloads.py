import sys
import abstra.dashes as abstra_dashes


class AuthResponse:
    """The response from the authentication process

    Attributes:
      email (str): The email address of the user
    """

    def __init__(self, email: str):
        self.email = email


def overload_stdio(broker):
    def writeWraper(type, write, text):
        try:
            write(text)
            broker.send({"type": type, "payload": text})
        finally:
            return len(text)

    stdout_write = sys.stdout.write
    stderr_write = sys.stderr.write

    sys.stdout.write = lambda text: writeWraper("stdout", stdout_write, text)
    sys.stderr.write = lambda text: writeWraper("stderr", stderr_write, text)


def overload_abstra_sdk(broker, _params):
    params = _params or {}

    def get_user():
        broker.send({"type": "auth:initialize"})
        while True:
            type, data = broker.recv()
            if type == "auth:validation-ended":
                return AuthResponse(data["email"])

    def redirect(url, query_params=params):
        broker.send({"type": "redirect", "url": url, "queryParams": query_params})

    def get_query_params():
        return params

    abstra_dashes.get_user = get_user
    abstra_dashes.redirect = redirect
    abstra_dashes.get_query_params = get_query_params
