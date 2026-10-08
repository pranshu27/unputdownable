from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """One instance per session. Inject a fresh AgentState() for each new user session."""

    inputs:       dict[str, Any]  = field(default_factory=dict)
    output_dir:   str             = ""
    files:        list[str]       = field(default_factory=list)
    errors:       list[str]       = field(default_factory=list)
    active_skill: str             = ""
    history:      list[dict]      = field(default_factory=list)

    def set_input(self, input_type: str, data: Any) -> None:
        self.inputs[input_type] = data
        self._reset_output()

    def get_input(self, input_type: str) -> Any:
        return self.inputs.get(input_type)

    def has_input(self, input_type: str) -> bool:
        return input_type in self.inputs and self.inputs[input_type] is not None

    def update_from_result(self, result: dict, skill_name: str) -> None:
        self.output_dir   = result.get("output_dir", "")
        self.files        = result.get("files",      [])
        self.errors       = result.get("errors",     [])
        self.active_skill = skill_name

    def push(self, role: str, content: Any) -> None:
        self.history.append({"role": role, "content": content})

    def reset(self) -> None:
        self.inputs  = {}
        self.history = []
        self._reset_output()

    def _reset_output(self) -> None:
        self.output_dir   = ""
        self.files        = []
        self.errors       = []
        self.active_skill = ""

    def input_summary(self) -> str:
        if not self.inputs: return "none"
        return ", ".join(f"{k}={'loaded' if v else 'empty'}" for k, v in self.inputs.items())
