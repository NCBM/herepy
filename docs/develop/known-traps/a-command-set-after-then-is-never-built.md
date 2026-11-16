# A command set after `then` is never built

A two-word literal path answered with the unknown-command error when its command was set on the last literal, and the
unit's handler never ran:

```
late: node=present command=null
late: threw SimpleCommandExceptionType message=Unknown command at position 16: ...ive reload<--[HERE]
```

## What `then` does at the call

`ArgumentBuilder.then(ArgumentBuilder)` builds the argument it is handed and attaches the built node. From brigadier
1.3.10, the jar the game loads, `javap -c com.mojang.brigadier.builder.ArgumentBuilder`:

```
  17: aload_0
  18: getfield      #4   // Field arguments:Lcom/mojang/brigadier/tree/RootCommandNode;
  21: aload_1
  22: invokevirtual #12  // Method build:()Lcom/mojang/brigadier/tree/CommandNode;
  25: invokevirtual #13  // Method RootCommandNode.addChild:(Lcom/mojang/brigadier/tree/CommandNode;)V
```

`executes` writes the builder's `command` field and `requires` writes its `requirement`; `LiteralArgumentBuilder.build`
copies both into a new `LiteralCommandNode`, together with the children the builder already accumulated. So a literal
is a template consumed once, when something attaches it, and a field set afterwards lands on a builder no node reads.
Nothing raises: the path still parses up to the last literal, and the parse ends with no command in the context.

## Why a one-word path hides it

`CommandDispatcher.register(LiteralArgumentBuilder)` builds its argument as well (bytecode offset 1,
`invokevirtual build`), after the caller has returned the builder. A one-word path hands that builder to `register`, so
an `executes` written last is still copied in. Every deeper literal is built by the `then` above it, which runs while
the chain is being assembled. The tree's only command had two words, so there was no working command to compare
against, and the failure read as a command that did not exist.

## What to write instead

Give each literal its `executes` and `requires` while it is still a builder, and attach last:

```java
builders.getFirst().requires(source -> source.hasPermission(permission));
// `then` builds the child it is handed, so the deepest literal is given its command before it is attached.
builders.getLast().executes(context -> {
    python.submit("commands.run", path, context.getSource());
    return 1;
});
for (int i = 0; i + 1 < builders.size(); i++) {
    builders.get(i).then(builders.get(i + 1));
}
return builders.getFirst();
```

The order is a property of the builder type, so it holds for any chain: `redirect` and `fork` are read by the same
`build` and are lost the same way.

## How this was measured

Two literals were chained with `executes` set after `then`, then registered on a fresh `CommandDispatcher`, then run
through `execute("scriptive reload", source)`: the node was found, `getCommand()` answered `null`, and the call threw.
The same chain built in the other order ran its handler and returned 1. Both runs used `brigadier-1.3.10.jar` from the game's libraries, the file the NeoForm `libraries.txt` names for this
build.

In the game, the dev dedicated server (`runs/server`) logged `Commands declared by units: [scriptive reload]` and the
input produced the unknown-command answer with no `scripts: reloaded` line; after the reorder the same input logged
`scripts: reloaded`. `tools/checks/check.py` covers none of this: it runs without a dispatcher.
