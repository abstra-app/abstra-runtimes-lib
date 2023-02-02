import os

# this stops hackerforms from opening a browser
original_runner = os.getenv("RUNNER")
os.environ["RUNNER"] = "dash"
from hackerforms.widget_utils import get_widget_class  # exported
from hackerforms.auth import AuthResponse  # exported

if original_runner:
    os.environ["RUNNER"] = original_runner
