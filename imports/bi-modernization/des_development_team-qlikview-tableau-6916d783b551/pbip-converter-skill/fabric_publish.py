"""
fabric_publish.py — Publish a generated PBIP folder to a Microsoft Fabric
workspace, binding the report to the published semantic model.

Usage
-----
    cd pbip-converter-skill
    # --workspace accepts EITHER the workspace GUID OR its display name
    python fabric_publish.py outputs/Shield_Insurance --workspace <GUID-or-name>

    # optional explicit names (default: the <Name> of the output folder)
    python fabric_publish.py outputs/Shield_Insurance \\
        --workspace "PBIP Migration" --model-name "Shield Model" --report-name "Shield Report"

Prerequisites
-------------
  * FABRIC_TENANT_ID / FABRIC_CLIENT_ID / FABRIC_CLIENT_SECRET in .env
  * the service principal is a Member/Admin of the target workspace
  * the workspace is on a Fabric (or Premium/trial) capacity
  * tenant setting "Service principals can use Fabric APIs" is enabled

What it does
------------
  1. creates the <Name>.SemanticModel folder as a Fabric semantic-model item,
  2. rewrites <Name>.Report/definition.pbir to live-connect to that model,
  3. creates the <Name>.Report folder as a Fabric report item,
  4. prints the in-service report URL.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from integrations.fabric_publisher import publish_pbip


def main():
    ap = argparse.ArgumentParser(
        description="Publish a generated PBIP folder to a Microsoft Fabric workspace.",
    )
    ap.add_argument("output_dir",
                    help="The generated PBIP folder (contains <Name>.SemanticModel "
                         "and <Name>.Report), e.g. outputs/Shield_Insurance")
    ap.add_argument("--workspace", "--workspace-id", dest="workspace", required=True,
                    help="Target Fabric workspace - its GUID or its display name.")
    ap.add_argument("--model-name", default=None,
                    help="Display name for the published semantic model "
                         "(default: the output folder's <Name>).")
    ap.add_argument("--report-name", default=None,
                    help="Display name for the published report "
                         "(default: the output folder's <Name>).")
    args = ap.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    if not os.path.isdir(output_dir):
        ap.error(f"output_dir not found: {output_dir}")

    # ASCII arrow on purpose — cmd.exe defaults to cp1252 and crashes with
    # UnicodeEncodeError if a non-ASCII glyph reaches stdout.
    print(f"\nPublishing {output_dir}\n  -> workspace {args.workspace}\n")
    try:
        result = publish_pbip(
            output_dir, args.workspace,
            model_name=args.model_name, report_name=args.report_name,
        )
    except Exception as exc:
        print(f"\n[x] Publish failed: {exc}\n")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  PUBLISHED")
    print("=" * 70)
    print(f"  semantic model : {result['model_name']}  ({result['model_id']})")
    print(f"  report         : {result['report_name']}  ({result['report_id']})")
    print(f"  open in cloud  : {result['report_url']}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
