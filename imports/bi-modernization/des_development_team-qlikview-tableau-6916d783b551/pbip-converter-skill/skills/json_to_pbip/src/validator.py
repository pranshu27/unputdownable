"""
validator.py — Validate a written .pbip output folder for required structure and keys.

Checks the modern PBIP format (matching Power BI Desktop export):
  - Name.pbip
  - Name.Report/.platform, definition.pbir, definition/version.json,
    definition/report.json, definition/pages/pages.json, definition/pages/*/page.json
  - Name.SemanticModel/.platform, definition.pbism,
    definition/model.tmdl, definition/database.tmdl, definition/tables/*.tmdl
"""
import json, os, argparse

REQUIRED_PAGE_KEYS  = {"name", "displayName", "width", "height"}
REQUIRED_VISUAL_KEYS = {"name", "position", "visual"}


def _long(path: str) -> str:
    """Prefix absolute Windows paths with `\\\\?\\` so MAX_PATH-bound Win32
    APIs (os.listdir, os.path.exists, os.path.isdir, open) can reach files
    under deep PBIP folder trees. Without this, valid output trees whose
    visual JSONs sit past 260 chars are reported as MISSING. No-op on POSIX.
    """
    if os.name == "nt" and os.path.isabs(path) and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.normpath(path)
    return path


def _exists(p): return os.path.exists(_long(p))
def _isdir(p):  return os.path.isdir(_long(p))
def _listdir(p): return os.listdir(_long(p))


def _load_json(path: str, errors: list) -> dict:
    try:
        with open(_long(path), encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"INVALID JSON: {path} — {e}")
        return {}


def validate(output_dir: str) -> list:
    errors = []

    # ── *.pbip file ───────────────────────────────────────────────────────────
    pbip_files = [f for f in _listdir(output_dir) if f.endswith(".pbip")]
    if not pbip_files:
        errors.append("MISSING: *.pbip file")
    else:
        pbip = _load_json(os.path.join(output_dir, pbip_files[0]), errors)
        if "artifacts" not in pbip:
            errors.append(f"{pbip_files[0]}: missing 'artifacts'")

    # ── *.Report folder ───────────────────────────────────────────────────────
    report_dirs = [d for d in _listdir(output_dir)
                   if d.endswith(".Report") and _isdir(os.path.join(output_dir, d))]
    if not report_dirs:
        errors.append("MISSING: *.Report folder")
    else:
        rdir = os.path.join(output_dir, report_dirs[0])
        rname = report_dirs[0]

        # .platform
        if not _exists(os.path.join(rdir, ".platform")):
            errors.append(f"MISSING: {rname}/.platform")

        # definition.pbir
        pbir_path = os.path.join(rdir, "definition.pbir")
        if not _exists(pbir_path):
            errors.append(f"MISSING: {rname}/definition.pbir")
        else:
            pbir = _load_json(pbir_path, errors)
            if "datasetReference" not in pbir:
                errors.append(f"{rname}/definition.pbir: missing 'datasetReference'")

        def_dir = os.path.join(rdir, "definition")

        # definition/version.json
        if not _exists(os.path.join(def_dir, "version.json")):
            errors.append(f"MISSING: {rname}/definition/version.json")

        # definition/report.json
        if not _exists(os.path.join(def_dir, "report.json")):
            errors.append(f"MISSING: {rname}/definition/report.json")

        # definition/pages/pages.json
        pages_dir = os.path.join(def_dir, "pages")
        pages_json = os.path.join(pages_dir, "pages.json")
        if not _exists(pages_json):
            errors.append(f"MISSING: {rname}/definition/pages/pages.json")
        else:
            pj = _load_json(pages_json, errors)
            if "pageOrder" not in pj:
                errors.append(f"{rname}/definition/pages/pages.json: missing 'pageOrder'")

        # page folders
        if _exists(pages_dir):
            page_folders = [d for d in _listdir(pages_dir)
                            if _isdir(os.path.join(pages_dir, d))]
            if not page_folders:
                errors.append(f"No page folders found under {rname}/definition/pages/")

            for pf in page_folders:
                pjson_path = os.path.join(pages_dir, pf, "page.json")
                if not _exists(pjson_path):
                    errors.append(f"MISSING: {rname}/definition/pages/{pf}/page.json")
                else:
                    pg = _load_json(pjson_path, errors)
                    for k in REQUIRED_PAGE_KEYS:
                        if k not in pg:
                            errors.append(f"{rname}/definition/pages/{pf}/page.json missing '{k}'")

                visuals_dir = os.path.join(pages_dir, pf, "visuals")
                if _exists(visuals_dir):
                    for vf in _listdir(visuals_dir):
                        vpath = os.path.join(visuals_dir, vf, "visual.json")
                        if not _exists(vpath):
                            errors.append(f"MISSING: .../{pf}/visuals/{vf}/visual.json")
                        else:
                            v = _load_json(vpath, errors)
                            for k in REQUIRED_VISUAL_KEYS:
                                if k not in v:
                                    errors.append(f".../{pf}/visuals/{vf}/visual.json missing '{k}'")

    # ── *.SemanticModel folder ────────────────────────────────────────────────
    model_dirs = [d for d in _listdir(output_dir)
                  if d.endswith(".SemanticModel") and _isdir(os.path.join(output_dir, d))]
    if not model_dirs:
        errors.append("MISSING: *.SemanticModel folder")
    else:
        mdir = os.path.join(output_dir, model_dirs[0])
        mname = model_dirs[0]

        # .platform
        if not _exists(os.path.join(mdir, ".platform")):
            errors.append(f"MISSING: {mname}/.platform")

        # definition.pbism
        if not _exists(os.path.join(mdir, "definition.pbism")):
            errors.append(f"MISSING: {mname}/definition.pbism")

        sdef = os.path.join(mdir, "definition")

        # model.tmdl + database.tmdl
        for tmdl in ("model.tmdl", "database.tmdl"):
            if not _exists(os.path.join(sdef, tmdl)):
                errors.append(f"MISSING: {mname}/definition/{tmdl}")

        # tables/*.tmdl
        tables_dir = os.path.join(sdef, "tables")
        if not _exists(tables_dir):
            errors.append(f"MISSING: {mname}/definition/tables/")
        else:
            tmdls = [f for f in _listdir(tables_dir) if f.endswith(".tmdl")]
            if not tmdls:
                errors.append(f"No *.tmdl files in {mname}/definition/tables/")

    return errors


def main():
    ap = argparse.ArgumentParser(description="Validate .pbip output folder")
    ap.add_argument("--input", required=True)
    args = ap.parse_args()

    errors = validate(args.input)
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  x {e}")
        exit(1)
    else:
        print("VALIDATION PASSED")


if __name__ == "__main__":
    main()
