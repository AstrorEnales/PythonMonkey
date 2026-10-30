/**
 * @file PyDictProxyHandler.cc
 * @author Caleb Aikens (caleb@distributive.network) and Philippe Laporte (philippe@distributive.network)
 * @brief Struct for creating JS proxy objects for Dicts
 * @date 2023-04-20
 *
 * @copyright Copyright (c) 2023-2024 Distributive Corp.
 *
 */

#include "include/PyDictProxyHandler.hh"

#include "include/jsTypeFactory.hh"
#include "include/pyTypeFactory.hh"

#include <jsapi.h>
#include <jsfriendapi.h>
#include <js/Conversions.h>
#include <js/Proxy.h>
#include <js/Symbol.h>
#include <js/friend/ErrorMessages.h>

#include <Python.h>



const char PyDictProxyHandler::family = 0;

bool PyDictProxyHandler::ownPropertyKeys(JSContext *cx, JS::HandleObject proxy, JS::MutableHandleIdVector props) const {
  PyObject *self = JS::GetMaybePtrFromReservedSlot<PyObject>(proxy, PyObjectSlot);
  PyObject *keys = PyDict_Keys(self);

  size_t length = PyList_Size(keys);

  bool success = handleOwnPropertyKeys(cx, keys, length, props);
  Py_DECREF(keys);
  return success;
}

bool PyDictProxyHandler::delete_(JSContext *cx, JS::HandleObject proxy, JS::HandleId id,
  JS::ObjectOpResult &result) const {
  PyObject *attrName = idToKey(cx, id);
  PyObject *self = JS::GetMaybePtrFromReservedSlot<PyObject>(proxy, PyObjectSlot);
  int status = PyDict_DelItem(self, attrName);
  Py_DECREF(attrName);
  if (status < 0) {
    return result.failCantDelete(); // raises JS exception
  }
  return result.succeed();
}

bool PyDictProxyHandler::has(JSContext *cx, JS::HandleObject proxy, JS::HandleId id,
  bool *bp) const {
  return hasOwn(cx, proxy, id, bp);
}

bool PyDictProxyHandler::getOwnPropertyDescriptor(
  JSContext *cx, JS::HandleObject proxy, JS::HandleId id,
  JS::MutableHandle<mozilla::Maybe<JS::PropertyDescriptor>> desc
) const {
  PyObject *attrName = idToKey(cx, id);
  PyObject *self = JS::GetMaybePtrFromReservedSlot<PyObject>(proxy, PyObjectSlot);
  PyObject *item = PyDict_GetItemWithError(self, attrName); // returns NULL without an exception set if the key wasn’t present.
  Py_DECREF(attrName);

  return handleGetOwnPropertyDescriptor(cx, id, desc, item);
}

bool PyDictProxyHandler::set(JSContext *cx, JS::HandleObject proxy, JS::HandleId id,
  JS::HandleValue v, JS::HandleValue receiver,
  JS::ObjectOpResult &result) const {
  JS::RootedValue rootedV(cx, v);
  PyObject *attrName = idToKey(cx, id);

  PyObject *self = JS::GetMaybePtrFromReservedSlot<PyObject>(proxy, PyObjectSlot);
  PyObject *value = pyTypeFactory(cx, rootedV);
  int status = PyDict_SetItem(self, attrName, value);
  Py_DECREF(attrName);
  Py_DECREF(value);
  if (status < 0) {
    return result.failCantSetInterposed(); // raises JS exception
  }
  return result.succeed();
}

bool PyDictProxyHandler::enumerate(JSContext *cx, JS::HandleObject proxy,
  JS::MutableHandleIdVector props) const {
  return this->ownPropertyKeys(cx, proxy, props);
}

bool PyDictProxyHandler::hasOwn(JSContext *cx, JS::HandleObject proxy, JS::HandleId id,
  bool *bp) const {
  PyObject *attrName = idToKey(cx, id);
  PyObject *self = JS::GetMaybePtrFromReservedSlot<PyObject>(proxy, PyObjectSlot);
  *bp = PyDict_Contains(self, attrName) == 1;
  Py_DECREF(attrName);
  return true;
}

bool PyDictProxyHandler::getOwnEnumerablePropertyKeys(
  JSContext *cx, JS::HandleObject proxy,
  JS::MutableHandleIdVector props) const {
  return this->ownPropertyKeys(cx, proxy, props);
}

bool PyDictProxyHandler::defineProperty(JSContext *cx, JS::HandleObject proxy,
  JS::HandleId id,
  JS::Handle<JS::PropertyDescriptor> desc,
  JS::ObjectOpResult &result) const {
  // Block direct `Object.defineProperty` since we already have the `set` method
  return result.failInvalidDescriptor();
}

bool PyDictProxyHandler::getBuiltinClass(JSContext *cx, JS::HandleObject proxy,
  js::ESClass *cls) const {
  *cls = js::ESClass::Object;
  return true;
}