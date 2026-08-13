from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class ToolSpec:
    name: str
    description: str
    required_args: list[str]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "required_args": tool.required_args,
            }
            for tool in self._tools.values()
        ]

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise ValueError(f"Tool `{name}` is not registered.")
        spec = self._tools[name]
        missing = [arg for arg in spec.required_args if arg not in args or args[arg] in (None, "")]
        if missing:
            raise ValueError(f"Tool `{name}` missing required args: {', '.join(missing)}")
        return spec.handler(args)
