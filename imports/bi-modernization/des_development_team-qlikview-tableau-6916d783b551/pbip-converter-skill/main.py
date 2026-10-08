"""
main.py — Wire the skill framework together.

Run the CLI:
    cd pbip-converter-skill
    python main.py

Or import build_agent() in app.py / chat_app.py.
"""
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ensure package root is on path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.llm_client    import AzureOpenAIClient
from core.skill_registry import SkillRegistry
from core.agent_state   import AgentState
from core.skill_agent   import SkillAgent
from skills.json_to_pbip.skill import JsonToPbipSkill


def build_agent() -> SkillAgent:
    """
    Factory — change skills or LLM backend here only.
    app.py and chat_app.py call this to get a ready agent.
    """
    llm = AzureOpenAIClient.from_env()

    registry = (
        SkillRegistry()
        .register(JsonToPbipSkill())
        # .register(AnotherSkill())   ← add more skills here, nothing else changes
    )

    state = AgentState()

    return SkillAgent(llm=llm, registry=registry, state=state, max_iter=5)


def run_cli():
    """Simple CLI to test the agent interactively."""
    agent = build_agent()
    print("Skill Agent ready. Upload JSON then chat. Ctrl+C to exit.\n")

    while True:
        try:
            input_type = input("Input type (json/skip): ").strip()
            if input_type == "json":
                path = input("Path to JSON file: ").strip()
                with open(path) as f:
                    agent.set_input("json", json.load(f))

            user_msg = input("\nYou: ").strip()
            if not user_msg:
                continue

            print("\nAgent: ", end="", flush=True)
            for chunk in agent.chat(user_msg):
                print(chunk, end="", flush=True)
            print("\n")

        except KeyboardInterrupt:
            print("\nExiting.")
            break


if __name__ == "__main__":
    run_cli()
