"""Python objects made for JS values are freed once Python drops them."""
import gc
import sys

import pythonmonkey as pm

CALLS = 20000


def retained_blocks(call):
  """Allocated blocks left behind by CALLS calls (a leak keeps at least one per call)."""
  for _ in range(100):
    call()
  gc.collect()
  before = sys.getallocatedblocks()
  for _ in range(CALLS):
    call()
  gc.collect()
  return sys.getallocatedblocks() - before


def test_numbers_returned_from_js_are_freed():
  number = pm.eval("() => 7.5")
  assert retained_blocks(number) < CALLS // 10


def test_strings_returned_from_js_are_freed():
  for text in ("latin1 text", "two-byte text €"):
    string = pm.eval(f"() => {text!r}.slice(0)")
    assert retained_blocks(string) < CALLS // 10


def test_function_proxies_are_freed():
  holder = pm.eval("({ method() { return true }, make() { return () => 1 } })")
  assert retained_blocks(lambda: holder.method) < CALLS // 10  # a bound JSFunctionProxy per lookup
  assert retained_blocks(lambda: holder.method()) < CALLS // 10
  assert retained_blocks(holder.make) < CALLS // 10


def test_js_assignment_past_the_end_of_a_python_list_keeps_the_value():
  for value in ("4", "'four'"):
    result = []
    pm.eval(f"(result) => {{ result[2] = {value} }}")(result)
    gc.collect()
    expected = pm.eval(f"() => {value}")()
    assert result[:2] == [None, None] and result[2] == expected


def test_method_proxies_are_freed():
  function = pm.eval("(function () { return this.value })")

  class Holder:
    value = 1

  holder = Holder()
  assert pm.JSMethodProxy(function, holder)() == 1
  assert retained_blocks(lambda: pm.JSMethodProxy(function, holder)) < CALLS // 10
