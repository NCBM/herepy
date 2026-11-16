# Known traps

Behaviour that costs a debugging session and that the code does not announce: each file names what was measured, the
source line that decides it, and what to write instead. A trap is not a decision, so a decision belongs in
[`docs/adr/`](../../adr/README.md).

| Trap | File |
|---|---|
| a static method costs one more argument than its signature | [a static method costs one more argument](a-static-method-costs-one-more-argument.md) |
| a Minecraft class name is not an import | [a Minecraft class arrives as an object](a-minecraft-class-is-not-an-import.md) |
