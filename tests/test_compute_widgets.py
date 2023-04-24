from abstra_runtimes.dashes_module.program import PythonProgram

dash_page_state = {"widgets": {"widgetA": {"value": None}, "widgetB": {"value": None}}}


def prepare_program(slot):
    program = PythonProgram(None)
    program.slot = slot
    return program


no_slots_layout = {
    "widgetA": {
        "id": "widgetA",
        "type": "text-input",
        "props": {"label": '"label"', "placeholder": '"placeholder"'},
        "events": {},
        "colEnd": 8,
        "rowEnd": 5,
        "colStart": 6,
        "rowStart": 3,
    }
}


def test_get_widget_simple_case():
    program = prepare_program(no_slots_layout)
    widget = program.get_widget("widgetA")
    assert widget == no_slots_layout["widgetA"]


one_grid_layout = {
    "gridBlock": {
        "id": "gridBlock",
        "type": "if-block",
        "row": 1,
        "height": 5,
        "order": 0,
        "props": {"condition": "True"},
        "slot": {
            "widgetA": {
                "id": "widgetB",
                "type": "text-input",
                "props": {"label": '"label"', "placeholder": '"placeholder"'},
                "events": {},
                "rowStart": 2,
                "rowEnd": 4,
                "colStart": 6,
                "colEnd": 8,
                "gridBlockId": "gridBlock",
            }
        },
    },
}


def test_get_widget_one_grid():
    program = prepare_program(one_grid_layout)
    widget = program.get_widget("widgetA")
    assert widget == one_grid_layout["gridBlock"]["slot"]["widgetA"]
