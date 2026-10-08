from .base_skill import BaseSkill


class SkillRegistry:
    """
    Single source of truth for all registered skills.

    Usage:
        registry = SkillRegistry()
        registry.register(JsonToPbipSkill())
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> "SkillRegistry":
        if not skill.name:
            raise ValueError("Skill must have a non-empty name.")
        self._skills[skill.name] = skill
        return self

    def unregister(self, skill_name: str) -> "SkillRegistry":
        self._skills.pop(skill_name, None)
        return self

    def resolve(self, tool_function_name: str) -> BaseSkill:
        skill_name = tool_function_name.removeprefix("run_")
        if skill_name not in self._skills:
            raise KeyError(
                f"No skill for tool '{tool_function_name}'. "
                f"Registered: {list(self._skills.keys())}"
            )
        return self._skills[skill_name]

    def all_tools(self) -> list[dict]:
        return [s.tool_definition for s in self._skills.values()]

    def router_prompt(self) -> str:
        lines = ["You are an automation agent. Available skills:\n"]
        for s in self._skills.values():
            lines.append(f"Tool: run_{s.name}")
            lines.append(f"Use : {s.description}\n")
        lines += [
            "## Rules",
            "- Match the user request to the best skill and call its tool.",
            "- If ambiguous ask ONE clarifying question. Call no tool yet.",
            "- Never call more than one tool per turn.",
        ]
        return "\n".join(lines)

    def __len__(self):  return len(self._skills)
    def __repr__(self): return f"SkillRegistry({list(self._skills.keys())})"
