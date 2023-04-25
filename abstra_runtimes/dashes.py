import websocket as ws, os, traceback, fire
from .broker import DashesBroker
from .utils import btos, read_file, prepate_traceback
from .overloads import overload_abstra_sdk, overload_stdio
from .dashes_module.program import PythonProgram, DashPageState


class MessageHandler:
    py: PythonProgram
    conn: DashesBroker
    dash_page_state: DashPageState

    def __init__(self, py: PythonProgram, broker: DashesBroker) -> None:
        self.py = py
        self.broker = broker
        self.dash_page_state = None

    def handle(self, type: str, data):
        handlers = {
            "broker-start": self.start,
            "widget-event": self.widget_event,
            "widgets-changed": self.widgets_changed,
            "eval": self.eval,
            "widget-input": self.widget_input,
            "autocomplete:load": self.autocomplete_load,
        }
        handler = handlers.get(type, self.default_handler)
        self.dash_page_state = data.get("state", self.dash_page_state)
        handler(data)

    def default_handler(self, _data):
        self.broker.send({"type": "error", "error": "unknown type"})

    def start(self, data):
        # data: { type: start, state: PAGESTATE, dashDefinition: DASHDEFINITION, params: PARAMS }
        self.py.slot = data["dashDefinition"]["slot"]
        overload_abstra_sdk(self.broker, data["params"])
        overload_stdio(self.broker)
        try:
            self.py.execute_initial_code()
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            self.broker.send(
                {
                    "type": "program-start-failed",
                    "error": traceback.format_exc(),
                    "stack": prepate_traceback(tb),
                }
            )
            exit()

        self._compute_and_send_widgets_props()

    def widget_input(self, data):
        # data: { type: widget-input, widgetId: string, state: PAGESTATE }
        if self.py.execute_widget_input(data["widgetId"]):
            self._compute_and_send_widgets_props()

    def widget_event(self, data):
        # data: { type: widget-event, widgetId: string, event: { type: string, payload: any }, state: PAGESTATE }
        if self.py.execute_widget_event(
            data["widgetId"],
            data["event"]["type"],
            data["event"].get("payload", {}),
            self.dash_page_state,
        ):
            self._compute_and_send_widgets_props()

    def eval(self, data):
        # data: {type: eval, expression: string}
        try:
            try:
                value = self.py.ev(data["expression"])
                self.broker.send({"type": "eval-return", "repr": repr(value)})
            except SyntaxError:
                self.py.ex(data["expression"])
                self.broker.send({"type": "eval-return", "repr": ""})
        except Exception as e:
            self.broker.send({"type": "eval-error", "repr": traceback.format_exc()})

        self._compute_and_send_widgets_props()

    def widgets_changed(self, data):
        # data: { type: widgets-changed, dashDefinition, state }
        self.py.slot = data["dashDefinition"]["slot"]
        self._compute_and_send_widgets_props()

    def autocomplete_load(self, data):
        # data: { type: autocomplete:load, suggestionsFor: string, code: string }
        try:
            suggestions = self.py.get_autocomplete_suggestions(data["code"])
        except Exception as e:
            suggestions = []

        self.broker.send(
            {
                "type": "autocomplete:suggestions",
                "suggestionsFor": data["suggestionsFor"],
                "suggestions": suggestions,
            }
        )

    def _compute_and_send_widgets_props(self):
        try:
            computed = self.py.evaluate_widgets(self.dash_page_state)
            self.broker.send({"type": "widgets-computed", **computed})
        except Exception as e:
            self.broker.send(
                {
                    "type": "widgets-computed",
                    "errors": {"general": {"repr": traceback.format_exc()}},
                }
            )


def __run__(code: str, execution_id: str):
    broker = DashesBroker(execution_id)
    py = PythonProgram(code)

    msg_handler = MessageHandler(py, broker)
    while True:
        try:
            type, data = broker.recv()
            msg_handler.handle(type, data)
        except ws.WebSocketConnectionClosedException:
            print("connection closed")
            exit()


class CLI(object):
    def run(self, **kwargs):
        execution_id = kwargs.get("execId") or os.getenv("EXECUTION_ID")
        if not execution_id:
            print("Missing EXECUTION_ID")
            exit()

        code = None
        if kwargs.get("file") or os.getenv("CODE_FILE_PATH"):
            code = read_file(kwargs.get("file") or os.getenv("CODE_FILE_PATH"))
        elif os.getenv("CODE"):
            code = btos(os.getenv("CODE"))

        if code == None:
            print("Missing CODE")
            exit()

        __run__(code, execution_id)


if __name__ == "__main__":
    fire.Fire(CLI)
