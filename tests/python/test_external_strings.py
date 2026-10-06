"""JS strings that share a Python string's buffer (JSExternalStrings)."""
import sys
import time

import pythonmonkey as pm


def release_finalized_strings():
  """Collect, then hand over one more string: references that finalized
  external strings give back are dropped on the next handover, with the GIL."""
  pm.collect()
  pm.collect()  # waits for the previous collection's background sweeping
  pm.eval("(s) => s.length")("release")


def test_round_trip_returns_the_same_object():
  identity = pm.eval("(s) => s")
  for string in ("".join(["external ", "latin1"]), "".join(["external ", "€"])):
    assert identity(string) is string


def test_reference_is_released_once_the_js_string_is_collected():
  for string in ("".join(["released ", "latin1"]), "".join(["released ", "€"])):
    before = sys.getrefcount(string)
    pm.eval("(s) => { globalThis.heldString = s; }")(string)
    assert sys.getrefcount(string) > before
    pm.eval("() => { delete globalThis.heldString; }")()
    release_finalized_strings()
    assert sys.getrefcount(string) == before


def test_many_external_strings_stay_linear():
  # Looking up and finalizing an external string used to scan every live one,
  # which made this quadratic (minutes); with a keyed table it takes seconds.
  identity = pm.eval("(s) => s")
  start = time.perf_counter()
  strings = [f"external string {i}" for i in range(100_000)]
  for string in strings:
    assert identity(string) is string
  del strings
  release_finalized_strings()
  assert time.perf_counter() - start < 10
