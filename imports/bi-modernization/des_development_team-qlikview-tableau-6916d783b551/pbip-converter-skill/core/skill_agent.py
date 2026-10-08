import json
from typing import Generator

from .base_skill import BaseSkill
from .skill_registry import SkillRegistry
from .agent_state import AgentState
from .llm_client import BaseLLMClient


class SkillAgent:
    """
    Reusable multi-skill agent.

    Phase 1 — Routing: LLM picks the right skill tool.
    Phase 2 — Execution: full SKILL.md context, pipeline runs, LLM explains result.
    """

    def __init__(self, llm: BaseLLMClient, registry: SkillRegistry,
                 state: AgentState, max_iter: int = 5):
        self._llm      = llm
        self._registry = registry
        self._state    = state
        self._max_iter = max_iter

    def set_input(self, input_type: str, data) -> None:
        self._state.set_input(input_type, data)

    def reset(self) -> None:
        self._state.reset()

    @property
    def state(self) -> AgentState:
        return self._state

    # Convenience properties for backwards-compatible access
    @property
    def output_dir(self) -> str:
        return self._state.output_dir

    @property
    def errors(self) -> list:
        return self._state.errors

    @property
    def files(self) -> list:
        return self._state.files

    def chat(self, user_message: str) -> Generator[str, None, None]:
        """
        Process one user turn. Yields text chunks. Manages history internally.

        Usage:
            for chunk in agent.chat("Convert my JSON to pbip"):
                print(chunk, end="", flush=True)
        """
        self._state.push("user", user_message)
        messages   = self._routing_messages()
        iterations = 0

        while iterations < self._max_iter:
            iterations += 1

            response = self._llm.chat(
                messages    = messages,
                tools       = self._registry.all_tools(),
                tool_choice = "auto",
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                content = msg.content or ""
                self._state.push("assistant", content)
                yield content
                break

            messages.append(self._serialise_msg(msg))

            for tc in msg.tool_calls:
                skill = self._registry.resolve(tc.function.name)
                yield f"⚙️  Running **{skill.display}**…\n\n"

                args = json.loads(tc.function.arguments or "{}")
                args["_input_data"] = self._state.get_input(skill.input_type)

                result     = skill.run(**args)
                result_str = json.dumps(result)

                self._state.update_from_result(result, skill.name)

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

                # Upgrade system prompt to full SKILL.md for execution phase
                messages[0] = {
                    "role":    "system",
                    "content": skill.build_execution_prompt(
                        input_data = self._state.get_input(skill.input_type),
                        state      = self._state,
                    ),
                }
        else:
            msg = f"⚠️  Max iterations ({self._max_iter}) reached. Please try again."
            self._state.push("assistant", msg)
            yield msg

    def _routing_messages(self) -> list[dict]:
        system = (
            self._registry.router_prompt()
            + f"\n\n## Session\nInputs: {self._state.input_summary()}\n"
            f"Last skill: {self._state.active_skill or 'None'}\n"
        )
        return [{"role": "system", "content": system}] + list(self._state.history)

    @staticmethod
    def _serialise_msg(msg) -> dict:
        d = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        return d
