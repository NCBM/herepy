# A static method costs one more argument than its signature

`ItemStack.isSameItem` is `public static boolean isSameItem(ItemStack, ItemStack)` in 1.21.1, so `a.isSameItem(b)`
raises from Python:

```
RuntimeError: Invalid number of arguments: 2, expected 3.
```

## What jep counts

jep puts the receiver into `args[0]` and then asks for `parameters + 1` arguments. From jep 4.4.0,
`src/main/c/Objects/pyjmethod.c:310`:

```c
lenJArgsExpected = PyJMethod_GetParameterCount(self, env);
lenJArgsNormal = lenJArgsExpected;
/* Python gives one more arg than java expects for self/this. */
if (lenJArgsNormal != lenPyArgsGiven - 1) {
    PyErr_Format(PyExc_RuntimeError, "Invalid number of arguments: %i, expected %i.",
                 (int) lenPyArgsGiven, lenJArgsExpected + 1);
```

`isStatic` is never read here, so a static method is charged for the receiver's slot as well. The call that fits
the signature fills that slot, and the callee ignores it.

## Why an overloaded name hides the trap

A name with several arities becomes a `PyJMultiMethod` (`pyjtype.c:308`), which picks the candidate whose parameter
count matches the call. A name with one signature has that layer nowhere, so the count has to fit exactly.
Measured through the same jep 4.4.0 on a JDK class, where `Integer.compare` is static and `String.substring` is
overloaded:

| call | result |
|---|---|
| `s.substring(1)` | `'ello'` |
| `s.substring(1, 3)` | `'el'` |
| `i.compare(1, 2)` | `-1` |
| `i.compare(1)` | `RuntimeError: Invalid number of arguments: 2, expected 3.` |
| `i.parseInt('7')` | `7` |

## What to write instead

Fill the receiver slot: `a.isSameItem(a, b)` reaches the static method with `(a, b)` and drops the receiver. A
wrapper that already holds both sides answers the same question with one comparison, which is what
`herecraft.api.items.ItemStack.is_same_item` does:

```python
return self.item == other.item
```

## How this was measured

The signatures come from `Class.getMethods()` over the client's NeoForm classpath, with `Class.forName(name, false,
loader)` so no static initializer runs. The calls ran through jep 4.4.0 on the interpreter this repository pins, whose
version `runtime/manifest.toml` states (ADR 0014). `tools/checks/check.py` covers none of this: it stands in for
`java.lang` and runs without jep.
