"""Python objects made for JS values are freed once Python drops them."""
import array
import asyncio
import gc
import sys

import pytest
import pythonmonkey as pm

CALLS = 20000

release_strings = pm.eval("(s) => 0")


def settle():
  """Collect garbage in both runtimes."""
  gc.collect()
  pm.collect()
  release_strings("release")  # Python strings JS let go of are released at the next str conversion
  gc.collect()


def retained_blocks(call, calls=CALLS):
  """Allocated blocks left behind by `calls` calls (a leak keeps at least one per call)."""
  for _ in range(100):
    call()
  settle()
  before = sys.getallocatedblocks()
  for _ in range(calls):
    call()
  settle()
  return sys.getallocatedblocks() - before


def retained_blocks_async(steps, count=2000):
  """Allocated blocks left behind by an event-loop run of `steps(count)`."""
  asyncio.run(steps(100))
  settle()
  before = sys.getallocatedblocks()
  asyncio.run(steps(count))
  settle()
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


# dict keys below are longer than one character: Python caches 1-character strings, which would hide leaked keys


def test_js_use_of_python_dicts_does_not_leak_keys():
  d = {"alpha": 1, "bravo": 2}
  for operation in ("d.alpha", "d.missing", "'alpha' in d", "Object.keys(d)", "JSON.stringify(d)",
                    "(d.xray = 1, delete d.xray)"):
    use = pm.eval(f"(d) => {operation}")
    assert retained_blocks(lambda: use(d)) < CALLS // 10, operation


def test_js_use_of_python_objects_does_not_leak():
  class Holder:
    base = 1.25

    @property
    def alpha(self):
      return self.base * 2  # a new float on every read

  holder = Holder()
  assert pm.eval("(o) => o.alpha")(holder) == 2.5
  for operation in ("o.alpha", "o.missing", "'alpha' in o", "Object.keys(o)", "(o.xray = 1, delete o.xray)"):
    use = pm.eval(f"(o) => {operation}")
    assert retained_blocks(lambda: use(holder)) < CALLS // 10, operation
  for value in (iter([1]), b"bytes"):  # proxies with their own property lookup
    use = pm.eval("(o) => o.missing")
    assert retained_blocks(lambda: use(value)) < CALLS // 10, value


def test_python_iterators_passed_to_js_are_released():
  iterator = iter([1, 2])
  before = sys.getrefcount(iterator)
  use = pm.eval("(it) => 0")
  for _ in range(100):
    use(iterator)
  gc.collect()
  pm.collect()  # finalizes the JS proxies, which release the iterator
  assert sys.getrefcount(iterator) == before
  assert pm.eval("(it) => it.next().value")(iterator) == 1


def test_iterating_js_objects_does_not_leak():
  obj = pm.eval("({ alpha: 1, bravo: 'two', charlie: { delta: 3 } })")
  assert list(obj.items()) == [("alpha", 1.0), ("bravo", "two"), ("charlie", {"delta": 3.0})]
  for iterate in (list, lambda o: list(o.keys()), lambda o: list(o.values()), lambda o: list(o.items()),
                  lambda o: list(reversed(o.items())), dict):
    assert retained_blocks(lambda: iterate(obj)) < CALLS // 10


def test_comparing_and_printing_js_objects_does_not_leak():
  obj = pm.eval("({ alpha: 1, bravo: 'two', charlie: { delta: 3 } })")
  same = {"alpha": 1.0, "bravo": "two", "charlie": {"delta": 3.0}}
  assert obj == same
  assert retained_blocks(lambda: obj == same) < CALLS // 10
  assert retained_blocks(lambda: repr(obj)) < CALLS // 10


def test_comparison_tells_apart_nested_js_objects_compared_to_the_same_dict():
  shared = {"value": 1.0}
  assert pm.eval("({ first: { value: 1 }, second: { value: 2 } })") != {"first": shared, "second": shared}


def test_updating_a_js_object_does_not_keep_it_alive():
  obj = pm.eval("({})")
  before = sys.getrefcount(obj)
  obj.update({"alpha": 1})
  obj.update(bravo=2)
  assert sys.getrefcount(obj) == before
  assert obj == {"alpha": 1.0, "bravo": 2.0}


def test_stepping_a_js_iterator_does_not_leak():
  counter = pm.eval("() => { let i = 0; return { next() { return { value: { i: i++ }, done: false } } } }")()
  assert next(counter) == {"i": 0.0}
  assert retained_blocks(lambda: next(counter)) < CALLS // 10
  with pytest.raises(StopIteration):
    next(pm.eval("({ next() { return { done: true } } })"))


def test_promise_jobs_and_timers_are_released():
  async def promise_steps(count):
    chain = pm.eval("(n) => { let p = Promise.resolve(0); for (let i = 0; i < n; i++) p = p.then(x => x + 1.5); return p }")
    assert await chain(count) == count * 1.5

  async def timeouts(count):
    wait = pm.eval("() => new Promise(resolve => setTimeout(resolve, 0))")
    for _ in range(count):
      await wait()

  async def cleared_timeouts(count):
    schedule_and_clear = pm.eval("() => clearTimeout(setTimeout(() => {}, 60000))")
    for _ in range(count):
      schedule_and_clear()

  async def awaited_python_coroutines(count):
    await_in_js = pm.eval("async (c) => await c")

    async def value():
      return 2.5
    for _ in range(count):
      assert await await_in_js(value()) == 2.5

  for steps in (promise_steps, timeouts, cleared_timeouts, awaited_python_coroutines):
    assert retained_blocks_async(steps) < 2000 // 10, steps.__name__


def test_errors_crossing_between_python_and_js_are_released():
  assert retained_blocks(pm.eval("() => new Error('failure in js')")) < CALLS // 10

  def fail_in_python():
    raise ValueError("failure in python")
  catch_in_js = pm.eval("(f) => { try { f() } catch (e) { return 1 } }")
  assert retained_blocks(lambda: catch_in_js(fail_in_python)) < CALLS // 10

  throw_in_js = pm.eval("() => { throw new Error('failure in js') }")
  assert retained_blocks(lambda: catch_in_js(lambda: throw_in_js())) < CALLS // 10  # rethrown through Python


def test_eval_options_and_require_are_released():
  filename = "some-module-file.js"
  module_globals = globals()
  before = sys.getrefcount(filename), sys.getrefcount(module_globals)
  for _ in range(100):
    pm.eval("1.5", {"filename": filename, "lineno": 3})
    pm.eval("1.5", {"fromPythonFrame": True})
  assert (sys.getrefcount(filename), sys.getrefcount(module_globals)) == before

  eval_from_js = pm.eval("(code) => pmEval(code, { filename: 'some-module-file.js', lineno: 3 })")
  assert retained_blocks(lambda: eval_from_js("1.5")) < CALLS // 10

  assert pm.eval("(a, b) => a === b")(pm.require("util"), pm.require("util"))  # loaded once, not on every call
  assert retained_blocks(lambda: pm.require("util"), calls=500) < 500 // 10


def test_eval_of_an_open_file_leaves_the_file_usable(tmp_path):
  script = tmp_path / "script.js"
  script.write_text("1.5 + 1")
  with open(script) as f:
    assert pm.eval(f) == 2.5
  # closing `f` failed with "Bad file descriptor" when eval closed the file's own descriptor


def test_js_array_operations_do_not_leak():
  arr = pm.eval("['alpha', 'bravo', 3.5]")
  assert retained_blocks(lambda: arr == ["alpha", "zulu", 3.5]) < CALLS // 10

  def out_of_range():
    with pytest.raises(IndexError):
      arr[99]
  assert retained_blocks(out_of_range) < CALLS // 10

  def extend():
    pm.eval("[]").extend(x * 1.5 for x in (1, 2, 3))
  assert retained_blocks(extend) < CALLS // 10

  def sort():
    pm.eval("['echo', 'delta', 'charlie']").sort(key=lambda s: s.upper())
  assert retained_blocks(sort) < CALLS // 10


def test_js_use_of_python_lists_does_not_leak():
  lst = ["alpha", "bravo", 2.5]
  for operation in ("l.splice(0, 0)", "(l.splice(1, 1, 'charlie'), l.splice(1, 1, 'bravo'))", "l.flatMap(x => [x])"):
    use = pm.eval(f"(l) => {operation}")
    assert retained_blocks(lambda: use(lst)) < CALLS // 10, operation
  assert lst == ["alpha", "bravo", 2.5]

  class Holder:
    def method(self, item):
      return item
  for_each = pm.eval("(l, f, t) => l.forEach(f, t)")
  assert retained_blocks(lambda: for_each(lst, Holder().method, {"key": 1})) < CALLS // 10


def test_js_flat_map_on_a_python_list():
  assert pm.eval("(l) => l.flatMap(x => [x + '!', 7.5])")(["ab", "cd"]) == ["ab!", 7.5, "cd!", 7.5]


def test_js_use_of_python_iterators_does_not_leak():
  spread = pm.eval("(it) => [...it].length")
  assert retained_blocks(lambda: spread(x * 1.5 for x in (1, 2, 3))) < CALLS // 10
  to_string = pm.eval("(it) => String(it)")
  assert retained_blocks(lambda: to_string(iter([1.5]))) < CALLS // 10


def test_mutable_buffers_passed_to_js_are_released():
  length = pm.eval("(b) => b.length")
  assert retained_blocks(lambda: length(bytearray(64))) < CALLS // 10
  assert retained_blocks(lambda: length(array.array("d", [1.5]))) < CALLS // 10
