# A Minecraft class arrives as an object, and its name is not an import

`from net.minecraft.world.item import Items` raises:

```
ImportError: java.lang.ClassNotFoundException: net.minecraft.world.item.Items
```

## Where the name is looked up

The import goes through jep's own importer (`jep/java_import_hook.py`): a package is answered from jep's class-name
list, and the class behind it is loaded by the class loader that importer was built with. The game's classes are
defined by ModLauncher's transforming loader, so a game class name reaches a loader that does not have it and arrives
as `ClassNotFoundException` — an import error that names a Java class rather than a module.

## What does see them

The context loader of the thread that crosses does. Measured on a dev client:

```python
from java.lang import Class, Thread

loader = Thread.currentThread().getContextClassLoader()  # cpw.mods.modlauncher.TransformingClassLoader
stacks = Class.forName("net.minecraft.world.item.ItemStack", False, loader)  # a PyJClass
```

The `False` carries weight: `initialize=True` runs the class's static initializer, and outside the game's own
bootstrap that is `IllegalArgumentException: Not bootstrapped` for `ItemStack`.

## What to write instead

Reach the game through what the mod hands over: `herecraft.api` wraps the types a unit works with, and every one of
them arrived as an object from Java. A unit that needs a class the bootstrap does not carry is asking for one more
entry in `herecraft.api._setup._bootstrap`, where Java can pass it over with the loader it already has.

## How this was measured

The import failure and the `Class.forName` call ran on the dev client (`runs/client`, `herecraft 0.1 on a client`).
The `initialize=true` failure came from a plain JVM over the NeoForm classpath, with no game.
