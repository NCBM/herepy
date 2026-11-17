"""herecraft.stubgen.overlay — Read what the class file does not carry: parameter names and docstrings.

The file is `build/stubgen/parchment.json`, which `./gradlew writeParchment` writes (ADR 0021). Its shape is
`{"source": {...}, "classes": {binary name: {"javadoc": [str], "methods": [{"name", "descriptor",
"parameters": [{"index", "name"}], "javadoc": [str]}]}}}`. A class name is the binary one, so a nested class keeps
its `$`; a method is keyed by its name and JVM descriptor, which is what separates two overloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Final, cast

from .javadoc import to_text

CONSTRUCTOR: Final = "<init>"


@dataclass(frozen=True)
class Method:
    """One method's entry: the doc, and the parameter names by the JVM slot they sit in."""

    doc: str = ""
    parameters: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Class:
    """One class's entry: its doc, and its methods keyed by name and descriptor."""

    doc: str = ""
    methods: dict[tuple[str, str], Method] = field(default_factory=dict)


class Overlay:
    """The data the build produced, answering by binary class name and by method name and descriptor."""

    source: Mapping[str, str]
    _classes: Mapping[str, Class]

    def __init__(self, data: Mapping[str, Any]) -> None:
        source = _mapping(data.get("source"))
        self.source = {key: str(value) for key, value in source.items()}
        self._classes = {str(name): _class(entry) for name, entry in _mapping(data.get("classes")).items()}

    @classmethod
    def load(cls, path: str | Path) -> Overlay:
        """Read the file the build wrote."""
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def class_doc(self, class_name: str) -> str:
        """The class's docstring text, or "" when the data has none."""
        found = self._classes.get(class_name)
        return found.doc if found is not None else ""

    def method_doc(self, class_name: str, name: str, descriptor: str) -> str:
        """The method's docstring text, or "" when the data has none."""
        found = self._method(class_name, name, descriptor)
        return found.doc if found is not None else ""

    def parameter_names(self, class_name: str, name: str, descriptor: str) -> dict[int, str]:
        """The parameter names by JVM local slot: 0 is `this`, and a long or a double takes two slots."""
        found = self._method(class_name, name, descriptor)
        return dict(found.parameters) if found is not None else {}

    def _method(self, class_name: str, name: str, descriptor: str) -> Method | None:
        found = self._classes.get(class_name)
        return found.methods.get((name, descriptor)) if found is not None else None


def _mapping(value: object) -> Mapping[str, Any]:
    """A JSON object as a mapping; anything else reads as empty, so one bad entry does not stop a run."""
    return cast("Mapping[str, Any]", value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _class(entry: object) -> Class:
    data = _mapping(entry)
    methods: dict[tuple[str, str], Method] = {}
    for raw in _sequence(data.get("methods")):
        method = _mapping(raw)
        name = method.get("name")
        descriptor = method.get("descriptor")
        if isinstance(name, str) and isinstance(descriptor, str):
            methods[(name, descriptor)] = Method(doc=_doc(method), parameters=_parameters(method))
    return Class(doc=_doc(data), methods=methods)


def _parameters(entry: Mapping[str, Any]) -> dict[int, str]:
    found: dict[int, str] = {}
    for raw in _sequence(entry.get("parameters")):
        parameter = _mapping(raw)
        index = parameter.get("index")
        name = parameter.get("name")
        if isinstance(index, int) and isinstance(name, str):
            found[index] = name
    return found


def _doc(entry: Mapping[str, Any]) -> str:
    """A `javadoc` list turned into docstring text; an entry without one, or of pure block tags, is empty."""
    return to_text(part for part in _sequence(entry.get("javadoc")) if isinstance(part, str))
