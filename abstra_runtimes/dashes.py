import websocket as ws, os, traceback, fire
from .broker import DashesBroker
from .utils import convert_answer, revert_value, btos, read_file, prepate_traceback
from .overloads import overload_abstra_sdk, overload_stdio
from abstra.widgets import (
    get_widget_class,
    is_prop_required,
    get_widget_name,
    get_prop_type,
)
from .autocomplete import get_suggestions


class PythonProgram:
    def __init__(self, code: str) -> None:
        # widgets: { [wid]: { type: string, props: {[prop]: expr}, events: {[evt]: cmd} } }
        self.widgets = None
        # state: { [variable: string]: value }
        self.state = {}
        # dash_page_state: { timestamp: int, widgets: { [widgetId: string]: { value: any } } }
        self.dash_page_state = None
        self.code = code

    def ex(self, cmd: str):
        exec(cmd, self.state, self.state)

    def ev(self, expr: str):
        return eval(expr, self.state, self.state)

    def execute_initial_code(self):
        if not self.code:
            return

        self.ex(self.code)

    def set_variable(self, variable: str, value):
        try:
            self.state.update({"__temp_value__": value})
            self.ex(f"{variable} = __temp_value__")
        except Exception as e:
            pass
        finally:
            self.state.pop("__temp_value__", None)

    def get_widget_context(self, wid):
        cls = get_widget_class(self.widgets[wid]["type"])
        value = self.dash_page_state["widgets"][wid]["value"]
        converted_value = convert_answer(cls, value)
        return cls, converted_value

    def execute_widget_event(self, wid, cmd, payload):
        _, widget_value = self.get_widget_context(wid)

        self.state.update({"__widget__": widget_value})
        self.state.update({"__event__": {"value": widget_value, "payload": payload}})

        try:
            self.ex(cmd)
        except Exception as e:
            traceback.print_exc()
            return {"repr": traceback.format_exc()}
        finally:
            self.state.pop("__widget__", None)
            self.state.pop("__event__", None)

    def evaluate_widgets(self):
        computed_widgets = {
            "stateTimestamp": self.dash_page_state.get("timestamp"),
            "props": {},
            "variables": {},
            "errors": {"widgets": {}, "props": {}, "variables": {}},
        }
        for wid, widget in self.widgets.items():
            widget_type = widget["type"]
            widget_class, widget_value = self.get_widget_context(wid)
            self.state.update({"__widget__": widget_value})

            props = {"key": "key"}
            errors = {}

            if widget.get("variable"):
                try:
                    # Check if it is a variable returning it's value
                    self.ev(widget["variable"])
                    self.ex(f'{widget["variable"]} = {widget["variable"]}')
                    variable_value = self.ev(widget["variable"])
                    computed_widgets["variables"][wid] = revert_value(
                        widget_class, variable_value
                    )

                except Exception as e:
                    computed_widgets["errors"]["variables"][wid] = {
                        "repr": traceback.format_exc()
                    }

            for prop, expr in widget["props"].items():
                if is_prop_required(widget_type, prop) and (
                    expr.strip() == "" or expr is None
                ):
                    prop_type = get_prop_type(widget_type, prop)
                    widget_name = get_widget_name(widget_type)
                    errors[prop] = {"repr": "Missing required prop"}
                    computed_widgets["errors"]["widgets"][wid] = {
                        "repr": f'Missing required prop "{prop}" ({prop_type}) for widget "{widget_name}".'
                    }
                    break

                try:
                    props[prop] = self.ev(expr) if expr else None
                except Exception as e:
                    errors[prop] = {"repr": traceback.format_exc()}
            else:
                try:
                    computed_widgets["props"][wid] = widget_class(**props).json()
                except Exception as e:
                    computed_widgets["errors"]["widgets"][wid] = {
                        "repr": traceback.format_exc()
                    }

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

    def get_autocomplete_suggestions(self, added_code_snippet):
        return get_suggestions(self.code, added_code_snippet)


class MessageHandler:
    py: PythonProgram
    conn: DashesBroker

    def __init__(self, py: PythonProgram, broker: DashesBroker) -> None:
        self.py = py
        self.broker = broker

    def handle(self, type: str, data):
        handlers = {
            "widgets-definition": self.widget_definition,
            "broker-start": self.start,
            "widget-event": self.widget_event,
            "widgets-changed": self.widgets_changed,
            "eval": self.eval,
            "widget-input": self.widget_input,
            "autocomplete:load": self.autocomplete_load,
        }
        handler = handlers.get(type, self.default_handler)
        self.py.dash_page_state = data.get("state", self.py.dash_page_state)
        handler(data)

    def default_handler(self, _data):
        self.broker.send({"type": "error", "error": "unknown type"})

    def widget_definition(self, data):
        # data: { type: widget-definition, widgets: { [wid]: { type: string, props: {[prop]: expr}, events: {[evt]: cmd} } } }
        self.py.widgets = data["widgets"]

    def start(self, data):
        # data: { type: start, state: PAGESTATE }
        self.py.widgets = data["widgetsDefinition"]
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
        widget_id = data["widgetId"]
        variable = self.py.widgets[widget_id].get("variable")

        if not variable:
            return

        _, value = self.py.get_widget_context(widget_id)
        self.py.set_variable(variable, value)
        self._compute_and_send_widgets_props()

    def widget_event(self, data):
        # data: { type: widget-event, widgetId: string, event: { type: string, payload: any }, state: PAGESTATE }
        widget_id = data["widgetId"]
        type = data["event"]["type"]
        cmd = self.py.widgets[widget_id]["events"].get(type)

        if not cmd:
            return

        payload = data["event"].get("payload", {})
        self.py.execute_widget_event(widget_id, cmd, payload)
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
        # data: { type: widgets-changed, widgets, state }
        self.py.widgets = data["widgets"]
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
            computed = self.py.evaluate_widgets()
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
