"""
chat_app.py — Streamlit chat UI powered by the Azure OpenAI PBIP Skill Agent.

The agent reads SKILL.md as its system context and uses function calling to
orchestrate the pipeline (parse → map → write → validate).

Run:
    cd pbip-converter-skill
    streamlit run chat_app.py
"""
import io, json, os, sys, zipfile
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import build_agent
from core.skill_agent import SkillAgent

st.set_page_config(
    page_title="PBIP Converter Agent",
    page_icon="🤖",
    layout="centered",
)

# ── Session state init ────────────────────────────────────────────────────────
if "agent" not in st.session_state:
    st.session_state.agent = build_agent()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_name" not in st.session_state:
    st.session_state.uploaded_name = None

agent: SkillAgent = st.session_state.agent

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Upload JSON")
    st.caption("Tableau or Power BI common-model export")
    uploaded = st.file_uploader("Choose file", type=["json"], label_visibility="collapsed")

    if uploaded:
        raw_bytes = uploaded.read()
        try:
            raw_json = json.loads(raw_bytes)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
            st.stop()

        # Only reset agent + notify chat when a new file is uploaded
        if uploaded.name != st.session_state.uploaded_name:
            agent.set_input("json", raw_json)
            st.session_state.uploaded_name = uploaded.name
            st.session_state.messages.append({
                "role": "assistant",
                "content": (
                    f"📂 **{uploaded.name}** loaded and ready.\n\n"
                    "Say **\"convert to .pbip\"** to run the full pipeline, "
                    "or ask me anything about the process."
                ),
            })
            st.rerun()

        st.success(f"✅ {uploaded.name}")

    st.divider()

    # ── Download button (appears after a successful conversion) ───────────────
    output_dir = agent.output_dir
    if output_dir and os.path.exists(output_dir):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, fnames in os.walk(output_dir):
                for fn in fnames:
                    full = os.path.join(root, fn)
                    arc  = os.path.relpath(full, os.path.dirname(output_dir))
                    zf.write(full, arc)
        zip_buf.seek(0)

        st.download_button(
            label="⬇️ Download .pbip as ZIP",
            data=zip_buf,
            file_name=f"{os.path.basename(output_dir)}.zip",
            mime="application/zip",
            type="primary",
        )

        errors = agent.errors
        if errors:
            st.warning(f"⚠️ {len(errors)} validation issue(s)")
            for e in errors:
                st.caption(f"• {e}")
        else:
            st.success("✅ Validation PASSED")

        files = agent.files
        if files:
            with st.expander(f"📋 {len(files)} files written"):
                st.code("\n".join(sorted(files)))

    st.divider()
    st.caption(
        "**How it works**\n\n"
        "1. Azure OpenAI reads `SKILL.md`\n"
        "2. Decides which pipeline steps to call\n"
        "3. Runs parse → map → write → validate\n"
        "4. Reports results here"
    )

# ── Main chat area ─────────────────────────────────────────────────────────────
st.title("🤖 PBIP Converter Agent")
st.caption("Azure OpenAI · SKILL.md-driven · function calling")

# Welcome message on first load
if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(
            "👋 Hi! I'm your PBIP Converter agent.\n\n"
            "**Upload a JSON file** in the sidebar, then tell me:\n"
            "- *\"Convert to .pbip\"* — runs the full pipeline\n"
            "- *\"Just run the parse step\"* — runs only parsing\n"
            "- *\"What does the mapper do?\"* — I'll explain\n\n"
            "I read `SKILL.md` to know exactly how to handle your file."
        )

# Render message history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Chat input ─────────────────────────────────────────────────────────────────
if prompt := st.chat_input("e.g. Convert to .pbip …"):
    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream agent response (history managed internally by AgentState)
    with st.chat_message("assistant"):
        full_response = st.write_stream(agent.chat(prompt))

    st.session_state.messages.append({"role": "assistant", "content": full_response})

    # Refresh sidebar to show download button if output is now ready
    if agent.output_dir:
        st.rerun()
