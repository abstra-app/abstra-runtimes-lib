from __future__ import annotations
from dataclasses import dataclass
from typing import Union
import traceback
from ..utils import convert_answer, revert_value, filter_object
from ..autocomplete import get_suggestions
from abstra.widgets import (
    get_widget_class,
    is_prop_required,
    get_widget_name,
    get_prop_type,
)

SLOTABLE_TYPES = ["if-block"]


@dataclass()
class DashPageState(dict):
    timestamp: int
    widgets: dict


@dataclass()
class Widget(dict):
    id: str
    type: str
    props: dict
    events: dict
    gridBlockId: str
    rowStart: int
    rowEnd: int
    colStart: int
    colEnd: int


@dataclass()
class GridBlock(dict):
    id: str
    type: str
    row: int
    height: int
    order: int
    props: dict
    slot: Slot


Slot = dict[str, Union[Widget, GridBlock]]
WidgetId = str


class PythonProgram:
    def __init__(self, code: str) -> None:
        # widgets: { [wid]: { type: string, props: {[prop]: expr}, events: {[evt]: cmd}, position: POSITION, gridBlockId } }
        self.slot = None
        # state: { [variable: string]: value }
        self.state = {}
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

    def get_widget_context(self, wid: Widget, dash_page_state: DashPageState):
        cls = get_widget_class(self.get_widget(wid)["type"])
        value = dash_page_state["widgets"].get(wid, {"value": None})["value"]
        converted_value = convert_answer(cls, value)
        return cls, converted_value

    def execute_widget_event(
        self, widget_id, type, payload, dash_page_state: DashPageState
    ):
        cmd = self.get_widget(widget_id)["events"].get(type)

        if not cmd:
            return False

        self.execute_widget_event_command(widget_id, cmd, payload, dash_page_state)
        return True

    def execute_widget_event_command(
        self, wid: Widget, cmd: str, payload, dash_page_state: DashPageState
    ):
        _, widget_value = self.get_widget_context(wid, dash_page_state)

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

    def execute_widget_input(self, widget_id, dash_page_state: DashPageState):
        variable = self.get_widget(widget_id).get("variable")

        if not variable:
            return False

        _, value = self.get_widget_context(widget_id, dash_page_state)
        self.set_variable(variable, value)
        return True

    def evaluate_widgets(self, dash_page_state: DashPageState):
        computed_widgets, computed_variables, errors = self.__compute_slot_widgets(
            self.slot, dash_page_state
        )
        return {
            "props": computed_widgets,
            "variables": computed_variables,
            "errors": errors,
            "stateTimestamp": dash_page_state.get("timestamp"),
        }

    def __compute_slot_widgets(self, slot: Slot, dash_page_state: DashPageState):
        computed_widgets = {}
        computed_variables = {}
        errors = {"props": {}, "variables": {}, "widgets": {}}

        for wid, widget in slot.items():
            if widget["type"] in SLOTABLE_TYPES:
                (
                    computed_slot,
                    computed_slot_variables,
                    errors_slot,
                ) = self.__compute_slot_widgets(widget["slot"], dash_page_state)
                (
                    widget_props,
                    props_errors,
                    widget_errors,
                ) = self.__compute_slottable_props(widget)
                computed_widgets = {**computed_widgets, **computed_slot}
                computed_variables = {**computed_variables, **computed_slot_variables}
                computed_widgets[wid] = widget_props
                if widget_errors:
                    errors["widgets"][wid] = widget_errors
                if props_errors:
                    errors["props"][wid] = props_errors

                merge_errors(errors, errors_slot)
            else:
                variable, props, widget_errors = self.__compute_widget(
                    wid, dash_page_state
                )
                computed_widgets[wid] = props
                computed_variables[wid] = variable
                if widget_errors["props"]:
                    errors["props"][wid] = widget_errors["props"]
                if widget_errors["variables"]:
                    errors["variables"][wid] = widget_errors["variables"]
                if widget_errors["widgets"]:
                    errors["widgets"][wid] = widget_errors["widgets"]

        return computed_widgets, computed_variables, errors

    def __compute_widget(self, wid: Widget, dash_page_state: DashPageState):
        widget_class, widget_value = self.get_widget_context(wid, dash_page_state)
        self.state.update({"__widget__": widget_value})
        errors = {"props": {}, "widgets": {}, "variables": {}}

        variable, errors["variables"] = self.__compute_widget_variable(
            self.get_widget(wid), widget_class
        )
        props, errors["props"], errors["widgets"] = self.__compute_widget_props(
            self.get_widget(wid), widget_class
        )

        self.state.pop("__widget__", None)
        return variable, props, errors

    def __compute_widget_props(self, widget: Widget, widget_class: str):
        props = {"key": "key"}
        props_errors = {}
        widget_errors = None
        result = None
        widget_type = widget["type"]
        for prop, expr in widget["props"].items():
            if is_prop_required(widget_type, prop) and (
                expr.strip() == "" or expr is None
            ):
                prop_type = get_prop_type(widget_type, prop)
                widget_name = get_widget_name(widget_type)
                props_errors[prop] = {"repr": "Missing required prop"}
                widget_errors = {
                    "repr": f'Missing required prop "{prop}" ({prop_type}) for widget "{widget_name}".'
                }
                break

            try:
                props[prop] = self.ev(expr) if expr else None
            except Exception as e:
                props_errors[prop] = {"repr": traceback.format_exc()}
        else:
            try:
                result = widget_class(**props).json()
            except Exception as e:
                widget_errors = {"repr": traceback.format_exc()}

        return result, props_errors, widget_errors

    def __compute_widget_variable(self, widget: Widget, widget_class: str):
        if not widget.get("variable"):
            return None, None

        try:
            # Check if it is a variable returning it's value
            self.ev(widget["variable"])
            self.ex(f'{widget["variable"]} = {widget["variable"]}')
            variable_value = self.ev(widget["variable"])
            return revert_value(widget_class, variable_value), None

        except Exception as e:
            return None, {"repr": traceback.format_exc()}

    def __widget_position(self, widget):
        return {
            "colStart": widget["colStart"],
            "colEnd": widget["colEnd"],
            "rowStart": widget["rowStart"],
            "rowEnd": widget["rowEnd"],
        }

    def __compute_slottable_props(self, widget: Widget):
        props = {}
        props_errors = {}
        widget_errors = None
        for prop, expr in widget["props"].items():
            try:
                props[prop] = self.ev(expr) if expr else None
            except Exception as e:
                props_errors[prop] = {"repr": traceback.format_exc()}

        return props, props_errors, widget_errors

    def __slottable_position(self, widget: Widget):
        return {
            "row": widget["row"],
            "height": widget["height"],
        }

    def get_widget(self, wid_id: WidgetId):
        return search_widget_in_slot(self.slot, wid_id)

    def get_autocomplete_suggestions(self, added_code_snippet):
        return get_suggestions(self.code, added_code_snippet)


def search_widget_in_slot(slot: Slot, widget_id: WidgetId):
    if slot.get(widget_id):
        return slot.get(widget_id)

    for widget in slot.values():
        if not widget.get("slot"):
            continue
        result = search_widget_in_slot(widget["slot"], widget_id)
        if result:
            return result

    return None


def merge_errors(errors, errors_slot):
    errors["props"] = {**errors["props"], **errors_slot["props"]}
    errors["variables"] = {**errors["variables"], **errors_slot["variables"]}
    errors["widgets"] = {**errors["widgets"], **errors_slot["widgets"]}
