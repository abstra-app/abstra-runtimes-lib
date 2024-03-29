import base64, json
from traceback import StackSummary
import simplejson


def serialize(obj):
    return simplejson.dumps(obj, ignore_nan=True)


def deserialize(st):
    return simplejson.loads(st)


def is_serializable(st):
    try:
        serialize(st)
        return True
    except:
        return False


def btos(b64):
    return base64.b64decode(b64).decode()


def get_staticmethod(cls, name):
    # hack because python sucks
    method_key = f"_{cls.__name__}{name}"
    return getattr(cls, method_key, None)


def convert_answer(cls, value):
    convert = get_staticmethod(cls, "__convert_answer")
    return convert(value) if convert else value


def revert_value(cls, value):
    revert = get_staticmethod(cls, "__revert_value")
    return revert(value) if revert else value


def read_file(filename: str):
    with open(filename, "r", encoding="utf8") as f:
        return f.read()


def filter_object(object, filter_func):
    filtered = {}
    for key, value in object.items():
        if filter_func(value):
            filtered[key] = value
    return filtered


def prepate_traceback(tb: StackSummary):
    for i, stack in enumerate(tb):
        if stack.filename == "<string>":
            return [{"line": x.lineno, "filename": x.filename} for x in tb[i:]]
    else:
        return []
