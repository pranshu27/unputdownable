"""
app.py — Streamlit frontend for the PBIP Converter Skill.

Run:
    cd pbip-converter-skill
    streamlit run app.py
"""
import io, json, os, shutil, sys, zipfile
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PBIP Converter",
    page_icon="📊",
    layout="centered",
)

st.title("📊 PBIP Converter Skill")
st.caption("Convert Tableau / Power BI JSON exports → Power BI `.pbip` format")

# ── Sidebar: mode & options ───────────────────────────────────────────────────
with st.sidebar:
    st.header("Options")
    mode = st.radio(
        "Input mode",
        ["Full pipeline (common-model JSON)", "Writer only (pre-mapped JSON)"],
        help=(
            "Full pipeline: raw Tableau/PBI export → parse → LLM map → write → validate.\n\n"
            "Writer only: skip parse/map, use an already-mapped JSON (e.g. mapped_pbi.json)."
        ),
    )
    report_name = st.text_input("Report name (optional)", placeholder="e.g. TruSecureCreDebit")
    source_override = st.selectbox(
        "Source override",
        ["Auto-detect", "powerbi", "tableau"],
    )
    skip_cache = st.checkbox("Skip cache", value=True)

# ── File uploader ─────────────────────────────────────────────────────────────
uploaded = st.file_uploader("Upload your JSON file", type=["json"])

if not uploaded:
    st.info("Upload a JSON file to get started.")
    st.stop()

# Show a quick preview of the uploaded file
raw_bytes = uploaded.read()
try:
    raw_json = json.loads(raw_bytes)
    with st.expander("📄 Uploaded JSON preview", expanded=False):
        st.json(raw_json, expanded=1)
except json.JSONDecodeError as e:
    st.error(f"Invalid JSON: {e}")
    st.stop()

# ── Convert button ────────────────────────────────────────────────────────────
if not st.button("🚀 Convert to .pbip", type="primary"):
    st.stop()

output_base = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(output_base, exist_ok=True)

errors: list = []
output_dir: str = ""
files: list = []

# ── Run pipeline ──────────────────────────────────────────────────────────────
if mode.startswith("Full pipeline"):
    try:
        from skills.json_to_pbip.src.parser    import parse_common_model, detect_source
        from skills.json_to_pbip.src.mapper    import map_intermediate
        from skills.json_to_pbip.src.writer    import write_pbip
        from skills.json_to_pbip.src.validator import validate
        from core.cache import SkillCache
        _cache = SkillCache(os.path.join(os.path.dirname(__file__), "cache", "cache_store.json"))

        with st.status("Running pipeline…", expanded=True) as status:

            # Step 0 — cache check
            st.write("🔍 Checking cache…")
            if not skip_cache:
                cached = _cache.get(raw_json)
                if cached and os.path.exists(cached):
                    st.write(f"✅ Cache hit → `{cached}`")
                    output_dir = cached
                    for root, _, fnames in os.walk(cached):
                        for fn in fnames:
                            files.append(os.path.relpath(os.path.join(root, fn), cached))
                    status.update(label="Done (cached)", state="complete")
                    st.stop()

            # Step 1 — parse
            st.write("📦 Step 1 — Parsing…")
            src = None if source_override == "Auto-detect" else source_override
            detected = src or detect_source(raw_json)
            intermediate = parse_common_model(raw_json, detected, None)
            if report_name:
                intermediate["report_name"] = report_name.replace(" ", "_")
                intermediate["original_name"] = report_name
            st.write(f"   ✅ Source: `{detected}` | Tables: {len(intermediate.get('tables', []))}")

            # Step 2 — map (LLM)
            st.write("🤖 Step 2 — Mapping with LLM (may take 20–60s)…")
            mapped = map_intermediate(intermediate)
            st.write(f"   ✅ Mapped `{mapped.get('reportName')}`")

            # Step 3 — write
            st.write("✍️  Step 3 — Writing .pbip…")
            name = mapped["reportName"]
            output_dir = os.path.join(output_base, name)
            files = write_pbip(mapped, output_dir)
            st.write(f"   ✅ Written {len(files)} files → `{output_dir}`")

            # Step 4 — validate
            st.write("🔎 Step 4 — Validating…")
            errors = validate(output_dir)
            if errors:
                st.write(f"   ⚠️ {len(errors)} validation issue(s)")
            else:
                st.write("   ✅ Validation PASSED")

            # Step 5 — cache save
            if not errors:
                _cache.set(raw_json, output_dir)

            status.update(
                label="✅ Conversion complete!" if not errors else "⚠️ Done with warnings",
                state="complete" if not errors else "error",
            )
    except Exception as e:
        st.error(f"Pipeline failed: {e}")
        st.stop()

else:
    # Writer-only mode — treat uploaded file as already-mapped JSON
    try:
        from skills.json_to_pbip.src.writer    import write_pbip
        from skills.json_to_pbip.src.validator import validate

        with st.status("Writing .pbip…", expanded=True) as status:
            st.write("✍️  Writing .pbip from pre-mapped JSON…")

            # Override report name if supplied
            if report_name:
                raw_json["reportName"] = report_name.replace(" ", "_")
                raw_json["originalName"] = report_name

            name = raw_json.get("reportName", "Report")
            output_dir = os.path.join(output_base, name)
            files = write_pbip(raw_json, output_dir)
            st.write(f"   ✅ Written {len(files)} files → `{output_dir}`")

            st.write("🔎 Validating…")
            errors = validate(output_dir)
            if errors:
                st.write(f"   ⚠️ {len(errors)} validation issue(s)")
            else:
                st.write("   ✅ Validation PASSED")

            status.update(
                label="✅ Done!" if not errors else "⚠️ Done with warnings",
                state="complete" if not errors else "error",
            )
    except Exception as e:
        st.error(f"Writer failed: {e}")
        st.stop()

# ── Results ───────────────────────────────────────────────────────────────────
st.divider()

if errors:
    st.error("### Validation issues")
    for e in errors:
        st.write(f"- {e}")
else:
    st.success("### Validation PASSED")

st.subheader(f"📁 Output: `{os.path.basename(output_dir)}`")
st.caption(f"Full path: `{output_dir}`")

with st.expander(f"📋 {len(files)} files written", expanded=False):
    st.code("\n".join(sorted(files)))

# ── Download ZIP ──────────────────────────────────────────────────────────────
zip_buf = io.BytesIO()
with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _, fnames in os.walk(output_dir):
        for fn in fnames:
            full = os.path.join(root, fn)
            arc = os.path.relpath(full, os.path.dirname(output_dir))
            zf.write(full, arc)
zip_buf.seek(0)

zip_name = f"{os.path.basename(output_dir)}.zip"
st.download_button(
    label="⬇️ Download .pbip as ZIP",
    data=zip_buf,
    file_name=zip_name,
    mime="application/zip",
    type="primary",
)

st.info(
    "**To open in Power BI Desktop:**  \n"
    "Unzip the downloaded file → Power BI Desktop → File → Open → select the `.pbip` file"
)
