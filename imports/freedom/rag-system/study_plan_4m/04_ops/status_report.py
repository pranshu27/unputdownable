import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    state_file = root / "06_state" / "progress.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))

    print("=== 4-Month Study Plan Status ===")
    print(f"As of: {state.get('as_of')}")
    print("")
    print("Top 3:")
    for key, val in state.get("top3", {}).items():
        print(f"- {key}: {val.get('status')} | {val.get('notes')}")
    print("")
    fp = state.get("four_month_plan", {})
    print("Plan:")
    print(f"- status: {fp.get('status')}")
    print(f"- current_phase: {fp.get('current_phase')}")
    print(f"- current_week_focus: {fp.get('current_week_focus')}")


if __name__ == "__main__":
    main()

