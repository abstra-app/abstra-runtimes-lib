import sys
import abstra.dashes as abstra_dashes
from hackerforms.auth import AuthResponse


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


def overload_abstra_sdk(broker):
    def get_user():
        broker.send({"type": "auth:initialize"})
        while True:
            type, data = broker.recv()
            if type == "auth:validation-ended":
                return AuthResponse(data["email"])

    abstra_dashes.get_user = get_user
