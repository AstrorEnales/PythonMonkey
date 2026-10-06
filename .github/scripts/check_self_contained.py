"""Check a bigheap wheel installed alone (pip install --no-deps: no pminit, no aiohttp).

  python check_self_contained.py plain   import pythonmonkey; require() and the
                                         XMLHttpRequest builtin work from the bundled
                                         node_modules
  python check_self_contained.py vendor  copy the package to _molfoundry_pm with only
                                         the import renames MolFoundry applies, remove
                                         pythonmonkey, and run the same checks on the
                                         copy (its version comes from _version.py)

The vendor stage deletes the installed pythonmonkey: run it in a throwaway venv.
"""
import importlib.util
import re
import shutil
import sys
from pathlib import Path

VENDOR_NAME = "_molfoundry_pm"
RENAMES = {
  ".py": [
    (re.compile(r"(?m)^(\s*)import pythonmonkey\b"), r"\1import " + VENDOR_NAME),
    (re.compile(r"(?m)^(\s*)from pythonmonkey\b"), r"\1from " + VENDOR_NAME),
  ],
  ".js": [
    (re.compile(r"""__import__\((['"])pythonmonkey\1\)"""), r"__import__(\1" + VENDOR_NAME + r"\1)"),
  ],
}


def exercise(pm, expected_version):
  assert importlib.util.find_spec("pminit") is None, "pminit must not be installed"
  assert importlib.util.find_spec("aiohttp") is None, "aiohttp must not be installed"
  assert pm.eval("1 + 1") == 2
  emitter = pm.new(pm.require("events"))()  # a package from the bundled node_modules
  assert pm.eval("(e) => typeof e.on")(emitter) == "function"
  assert pm.eval("typeof XMLHttpRequest") == "function"
  assert pm.__version__ == expected_version, (pm.__version__, expected_version)
  print(f"{pm.__name__} {pm.__version__}: eval, require('events') and XMLHttpRequest work "
        "without pminit or aiohttp")


def vendor(source: Path) -> Path:
  target = source.parent / VENDOR_NAME
  shutil.rmtree(target, ignore_errors=True)
  shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
  for path in target.rglob("*"):
    if path.suffix in RENAMES and "node_modules" not in path.relative_to(target).parts:
      text = path.read_text(encoding="utf-8")
      for pattern, replacement in RENAMES[path.suffix]:
        text = pattern.sub(replacement, text)
      path.write_text(text, encoding="utf-8")
  shutil.rmtree(source)
  for dist_info in source.parent.glob("pythonmonkey-*.dist-info"):
    shutil.rmtree(dist_info)
  return target


def main(stage):
  import importlib.metadata
  expected_version = importlib.metadata.version("pythonmonkey")
  if stage == "plain":
    import pythonmonkey as pm
    exercise(pm, expected_version)
  elif stage == "vendor":
    vendor(Path(importlib.util.find_spec("pythonmonkey").origin).parent)
    importlib.invalidate_caches()
    assert importlib.util.find_spec("pythonmonkey") is None
    pm = importlib.import_module(VENDOR_NAME)
    exercise(pm, expected_version)
  else:
    raise SystemExit(f"unknown stage {stage!r}; use plain or vendor")


if __name__ == "__main__":
  main(sys.argv[1])
