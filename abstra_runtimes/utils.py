import base64, json


def serialize(obj):
    return json.dumps(obj)


def deserialize(st):
    return json.loads(st)


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
