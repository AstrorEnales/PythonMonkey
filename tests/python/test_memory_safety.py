"""Values stay valid for as long as either runtime can still reach them (each of these used to crash)."""
import gc
import sys

import pytest
import pythonmonkey as pm


def collect():
  gc.collect()
  pm.collect()
  gc.collect()


def test_ordering_two_different_js_arrays():
  assert pm.eval("[1, 2]") < pm.eval("[1, 3]")
  assert not (pm.eval("[1, 3]") <= pm.eval("[1, 2]"))


def test_in_place_concatenation_of_a_js_array():
  arr = pm.eval("['alpha']")
  arr += ("bravo", "charlie")
  arr += pm.eval("['delta']")
  arr += (x for x in ["echo"])
  assert arr == ["alpha", "bravo", "charlie", "delta", "echo"]
  with pytest.raises(TypeError):
    arr += 5


def test_js_shift_of_a_python_list():
  items = ["unique-" + str(i) * 3 for i in range(5)]  # only the list refers to these strings
  shift = pm.eval("(l) => l.shift()")
  assert [shift(items) for _ in range(5)] == ["unique-" + str(i) * 3 for i in range(5)]


def test_js_copy_within_a_python_list():
  item = {"key": 1}
  items = [item, None]
  before = sys.getrefcount(item)
  pm.eval("(l) => { l.copyWithin(1, 0, 1) }")(items)
  assert items == [item, item]
  assert sys.getrefcount(item) == before + 1


def test_js_iterators_keep_their_python_source_alive():
  cases = (
    ("(l) => l.values()", lambda: [1.5, 2.5], 1.5),
    ("(it) => it[Symbol.iterator]()", lambda: iter([1.5, 2.5]), 1.5),
    ("(b) => b[Symbol.iterator]()", lambda: b"abc", 97.0),
  )
  for code, make_source, first in cases:
    iterator = pm.eval(code)(make_source())  # nothing but the iterator refers to the source's proxy
    collect()
    reuse_freed_memory = [bytearray(64) for _ in range(10000)]
    assert iterator.next()["value"] == first, code
    del reuse_freed_memory


def test_empty_bytes_in_js():
  assert pm.eval("(b) => b.toString()")(b"") == ""


def test_js_symbols_cannot_be_put_into_python_lists():
  for operation in ("l.push(sym)", "l.unshift(sym)", "l.concat([sym])", "l.splice(0, 0, sym)", "l.fill(sym)",
                    "l.indexOf(sym)", "l.lastIndexOf(sym)", "(l[0] = sym)"):
    with pytest.raises(TypeError):
      pm.eval(f"(l) => {{ const sym = Symbol('s'); {operation} }}")(["alpha"])
