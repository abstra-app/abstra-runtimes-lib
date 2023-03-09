import websocket as ws, os

from .utils import serialize, deserialize


DASHES_WS_HOST = os.getenv("DASHES_WS_HOST", "wss://dashes-broker.abstra.cloud")


class DashesBroker:
    def __init__(self, execution_id) -> None:
        self.conn = ws.create_connection(
            f"{DASHES_WS_HOST}/lib?executionId={execution_id}"
        )

    def send(self, data):
        self.conn.send(serialize(data))

    def recv(self):
        data = deserialize(self.conn.recv())
        return data["type"], data

    def close(self):
        self.conn.close()
