# Export public PythonMonkey APIs
from .pythonmonkey import *
from .helpers import *
from .require import *

# Expose the package version
import importlib.metadata
try:
  __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:  # vendored under another name
  from ._version import __version__
del importlib

# Load the module by default to expose global APIs
# builtin_modules
require("console")
require("base64")
require("timers")
require("url")
require("XMLHttpRequest")
