from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import json


class BaseSkill(ABC):
    """
    Every skill inherits this.
    Fill the 6 class-level fields + implement run() = fully working skill.
    """

    name: str          = ""
    display: str       = ""
    description: str   = ""
    input_type: str    = ""
    skill_md_path: str = ""

    tool_params: dict   = {}
    tool_required: list = []

    @property
    def tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name":        f"run_{self.name}",
                "description": self.description,
                "parameters": {
                    "type":       "object",
                    "properties": self.tool_params,
                    "required":   self.tool_required,
                },
            },
        }

    def load_skill_md(self) -> str:
        path = Path(self.skill_md_path)
        if not path.exists():
            raise FileNotFoundError(f"[{self.name}] SKILL.md not found: {self.skill_md_path}")
        return path.read_text(encoding="utf-8")

    def build_execution_prompt(self, input_data: Any, state: "AgentState") -> str:
        skill_md    = self.load_skill_md()
        input_block = self._fmt_input(input_data)
        state_block = self._fmt_state(state)
        return f"{skill_md}\n\n---\n{input_block}\n{state_block}"

    @abstractmethod
    def run(self, **kwargs) -> dict:
        """
        Execute this skill's pipeline.
        Must return: { "output_dir": str, "files": list[str], "errors": list[str] }
        """

    def _fmt_input(self, data: Any) -> str:
        if data is None:
            return "## Current Input\nNo input loaded."
        if isinstance(data, dict):
            return f"## Current Input ({self.input_type})\n```json\n{json.dumps(data, indent=2)[:3000]}\n```"
        return f"## Current Input ({self.input_type})\n{str(data)[:3000]}"

    @staticmethod
    def _fmt_state(state: "AgentState") -> str:
        return (
            f"## Pipeline State\n"
            f"Output dir : {state.output_dir or 'Not yet generated'}\n"
            f"Files      : {state.files      or 'None'}\n"
            f"Errors     : {state.errors     or 'None'}\n"
        )
