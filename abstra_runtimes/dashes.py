import websocket as ws, os, sys, traceback

from .broker import DashesBroker
from .utils import convert_answer, revert_value, btos
from hackerforms.widget_utils import get_widget_class


class PythonProgram:
    def __init__(self, code: str) -> None:
        # widgets: { [wid]: { type: string, props: {[prop]: expr}, events: {[evt]: cmd} } }
        self.widgets = None
        self.state = {}
        if code:
            self.ex(code)

    def ex(self, cmd: str):
        exec(cmd, self.state, self.state)

    def ev(self, expr: str):
        return eval(expr, self.state, self.state)

    def set_variable(self, variable: str, value):
        try:
            self.state.update({"__temp_value__": value})
            self.ex(f"{variable} = __temp_value__")
        except Exception as e:
            pass
        finally:
            self.state.pop("__temp_value__", None)

    def get_widget_context(self, state, wid):
        cls = get_widget_class(self.widgets[wid]["type"])
        value = state["widgets"][wid]["value"]
        converted_value = convert_answer(cls, value)
        return cls, converted_value

    def execute_widget_event(self, wid, cmd, state):
        # state: { widgets: { [widgetId: string]: { value: any } } }
        _, widget_value = self.get_widget_context(state, wid)

        self.state.update({"__widget__": widget_value})
        self.state.update({"__event__": {"value": widget_value}})

        try:
            self.ex(cmd)
        except Exception as e:
            traceback.print_exc()
            return {"repr": repr(e)}
        finally:
            self.state.pop("__widget__", None)
            self.state.pop("__event__", None)

    def evaluate_widgets(self, state):
        # state: { timestamp: int, widgets: { [widgetId: string]: { value: any } } }
        computed_widgets = {
            "stateTimestamp": state.get("timestamp"),
            "props": {},
            "variables": {},
            "errors": {"widgets": {}, "props": {}, "variables": {}},
        }
        for wid, widget in self.widgets.items():
            widget_class, widget_value = self.get_widget_context(state, wid)
            self.state.update({"__widget__": widget_value})

            props = {"key": "key"}
            errors = {}

            if widget.get("variable"):
                try:
                    # Check if it is a variable returning it's value
                    variable_value = self.ev(
                        f'({widget["variable"]} := {widget["variable"]})'
                    )
                    computed_widgets["variables"][wid] = revert_value(
                        widget_class, variable_value
                    )

                except Exception as e:
                    computed_widgets["errors"]["variables"][wid] = {"repr": repr(e)}

            for prop, expr in widget["props"].items():
                try:
                    props[prop] = self.ev(expr) if expr else None
                except Exception as e:
                    errors[prop] = {"repr": repr(e)}
            try:
                computed_widgets["props"][wid] = widget_class(**props).json()
            except Exception as e:
                computed_widgets["errors"]["widgets"][wid] = {"repr": repr(e)}
            computed_widgets["errors"]["props"][wid] = errors

        self.state.pop("__widget__", None)
        return computed_widgets
        """
        {
            'props': { [widgetId: string]: { [prop: string]: string } },
            'variables': { [widgetId: string]: any },
            'errors': {
                'widgets':   { [widgetId: string]: { 'repr': string } },
                'variables': { [widgetId: string]: { 'repr': string } },
                'props':     { [widgetId: string]: { [prop: string]: {'repr': string } } 
            },
        }
        """


class MessageHandler:
    py: PythonProgram
    conn: DashesBroker

    def __init__(self, py: PythonProgram, broker: DashesBroker) -> None:
        self.py = py
        self.broker = broker

    def handle(self, type: str, data):
        handlers = {
            "widgets-definition": self.widget_definition,
            "start": self.start,
            "widget-event": self.widget_event,
            "widgets-changed": self.widgets_changed,
            "eval": self.eval,
            "widget-input": self.widget_input,
        }
        handler = handlers.get(type, self.default_handler)
        handler(data)

    def default_handler(self, _data):
        self.broker.send({"type": "error", "error": "unknown type"})

    def widget_definition(self, data):
        # data: { type: widget-definition, widgets: { [wid]: { type: string, props: {[prop]: expr}, events: {[evt]: cmd} } } }
        self.py.widgets = data["widgets"]

    def start(self, data):
        # data: { type: start, state: PAGESTATE }
        self._compute_and_send_widgets_props(data["state"])

    def widget_input(self, data):
        # data: { type: widget-input, widgetId: string, state: PAGESTATE }
        state = data["state"]
        widget_id = data["widgetId"]
        variable = self.py.widgets[widget_id].get("variable")

        if not variable:
            return

        _, value = self.py.get_widget_context(state, widget_id)
        self.py.set_variable(variable, value)
        self._compute_and_send_widgets_props(state)

    def widget_event(self, data):
        # data: { type: widget-event, widgetId: string, event: { type: string }, state: PAGESTATE }
        state = data["state"]
        widget_id = data["widgetId"]
        type = data["event"]["type"]

        cmd = self.py.widgets[widget_id]["events"].get(type)
        if cmd:
            self.py.execute_widget_event(widget_id, cmd, state)
        self._compute_and_send_widgets_props(state)

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
            self.broker.send({"type": "eval-error", "repr": repr(e)})

        self._compute_and_send_widgets_props(data["state"])

    def widgets_changed(self, data):
        # data: { type: widgets-changed, widgets, state }
        self.py.widgets = data["widgets"]
        self._compute_and_send_widgets_props(data["state"])

    def _compute_and_send_widgets_props(self, state):
        try:
            computed = self.py.evaluate_widgets(state)
            self.broker.send({"type": "widgets-computed", **computed})
        except Exception as e:
            self.broker.send(
                {"type": "widgets-computed", "errors": {"general": {"repr": repr(e)}}}
            )


def run(code, execution_id):
    broker = DashesBroker(execution_id)

    try:
        py = PythonProgram(btos(code))
        broker.send({"type": "program-ready"})
    except Exception as e:
        broker.send({"type": "program-start-failed", "error": repr(e)})
        exit()

    msg_handler = MessageHandler(py, broker)
    while True:
        try:
            type, data = broker.recv()
            msg_handler.handle(type, data)
        except ws.WebSocketConnectionClosedException:
            print("connection closed")
            exit()


if __name__ == "__main__":
    if sys.argv[1] == "run":
        code = os.getenv("CODE")
        execution_id = os.getenv("EXECUTION_ID")

        if not code or not execution_id:
            print("Missing CODE or EXECUTION_ID")
            exit()

        run(code, execution_id)
    else:
        print("Unknown command")
        exit()
