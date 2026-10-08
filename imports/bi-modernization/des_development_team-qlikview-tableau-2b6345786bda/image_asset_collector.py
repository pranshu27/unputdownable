"""
Image Asset Collector
---------------------
Collects and base64-encodes image assets from Power BI (.pbix) and Tableau (.twbx) files.

This module provides two functions:
  - collect_powerbi_image_assets(pbix_extracted_dir) → for Power BI
  - collect_tableau_image_assets(twbx_bytes)         → for Tableau

Both return a list of dicts with base64-encoded image data ready to be
injected into the output JSON for forward engineering.

Usage:
    from image_asset_collector import collect_powerbi_image_assets, collect_tableau_image_assets

    # Power BI — pass the directory where the .pbix was extracted
    assets = collect_powerbi_image_assets("/path/to/extracted_files/powerbi_session_xxx")

    # Tableau — pass the raw .twbx file bytes
    assets = collect_tableau_image_assets(twbx_file_bytes)

    # Inject into your output JSON
    result["image_assets"] = assets
"""

import base64
import io
import json
import mimetypes
import zipfile
from pathlib import Path
from typing import List, Dict, Any


# Image file extensions we recognize
_IMAGE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.jfif', '.jpe', '.gif', '.svg', '.svgz',
    '.bmp', '.ico', '.webp', '.tiff', '.tif', '.heic', '.heif',
    '.avif', '.raw', '.cr2', '.nef', '.orf', '.sr2', '.arw',
    '.dng', '.psd', '.ai', '.eps', '.pdf', '.emf', '.wmf',
    '.pcx', '.tga', '.exr', '.hdr', '.pbm', '.pgm', '.ppm',
    '.xbm', '.xpm', '.cur', '.ani', '.apng',
}


def _get_content_type(filename: str) -> str:
    """Guess MIME content type from filename."""
    ct = mimetypes.guess_type(filename)[0]
    if ct:
        return ct
    ext = Path(filename).suffix.lower().lstrip('.')
    return f"image/{ext}" if ext else "application/octet-stream"


def _is_image_file(filename: str) -> bool:
    """Check if a filename has an image extension."""
    return Path(filename).suffix.lower() in _IMAGE_EXTENSIONS


# =============================================================================
# POWER BI — collect from extracted .pbix directory
# =============================================================================

def collect_powerbi_image_assets(pbix_extracted_dir: str) -> List[Dict[str, Any]]:
    """
    Collect and base64-encode all image assets from an extracted PBIX directory.

    Scans Report/StaticResources/RegisteredResources/ (and parent) for image files,
    reads them, and returns base64-encoded data.

    Args:
        pbix_extracted_dir: Path to the directory where the .pbix ZIP was extracted.

    Returns:
        List of dicts:
        [
            {
                "filename": "logo.png",
                "relative_path": "Report/StaticResources/RegisteredResources/logo.png",
                "size_bytes": 8432,
                "content_type": "image/png",
                "data_base64": "iVBORw0KGgoAAAANSUhEUg..."
            }
        ]
    """
    base_dir = Path(pbix_extracted_dir)
    assets: List[Dict[str, Any]] = []

    # Power BI stores images in these locations
    resource_dirs = [
        base_dir / "Report" / "StaticResources" / "RegisteredResources",
        base_dir / "Report" / "StaticResources",
    ]

    seen_files = set()  # avoid duplicates if nested scan overlaps

    for resource_dir in resource_dirs:
        if not resource_dir.exists():
            continue
        for file_path in resource_dir.iterdir():
            if not file_path.is_file():
                continue
            if not _is_image_file(file_path.name):
                continue
            if file_path.name in seen_files:
                continue
            seen_files.add(file_path.name)

            try:
                file_bytes = file_path.read_bytes()
                assets.append({
                    "filename": file_path.name,
                    "relative_path": str(file_path.relative_to(base_dir)).replace("\\", "/"),
                    "size_bytes": len(file_bytes),
                    "content_type": _get_content_type(file_path.name),
                    "data_base64": base64.b64encode(file_bytes).decode("ascii"),
                })
            except (OSError, IOError) as e:
                print(f"[image_asset_collector] Warning: Could not read {file_path}: {e}")

    if assets:
        total_size = sum(a["size_bytes"] for a in assets)
        print(f"[image_asset_collector] Power BI: collected {len(assets)} images "
              f"({total_size:,} bytes total, ~{total_size * 4 // 3:,} bytes base64)")

    return assets


# =============================================================================
# TABLEAU — collect from .twbx ZIP archive bytes OR .twb XML bytes
# =============================================================================

def collect_tableau_image_assets(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Collect and base64-encode all image assets from a Tableau file.

    Handles both:
    - .twbx (ZIP archive): extracts bundled image files and base64-encodes them
    - .twb (plain XML): extracts bitmap zone references (local file paths) and
      inline thumbnail images (already base64 in the XML)

    Args:
        file_bytes: Raw bytes of the uploaded .twb or .twbx file.

    Returns:
        List of dicts:
        [
            {
                "filename": "background.png",
                "archive_path": "Image/background.png",  # for .twbx
                "source_path": "C:/Users/.../bg.png",    # for .twb bitmap refs
                "size_bytes": 15200,
                "content_type": "image/png",
                "data_base64": "iVBORw0KGgoAAAANSUhEUg...",
                "asset_type": "bundled" | "thumbnail" | "external_reference"
            }
        ]
    """
    if zipfile.is_zipfile(io.BytesIO(file_bytes)):
        return _collect_from_twbx(file_bytes)
    else:
        return _collect_from_twb(file_bytes)


def _collect_from_twbx(twbx_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract image files from a .twbx ZIP archive."""
    assets: List[Dict[str, Any]] = []

    with zipfile.ZipFile(io.BytesIO(twbx_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not _is_image_file(info.filename):
                continue

            try:
                img_bytes = zf.read(info.filename)
                assets.append({
                    "filename": Path(info.filename).name,
                    "archive_path": info.filename,
                    "size_bytes": len(img_bytes),
                    "content_type": _get_content_type(info.filename),
                    "data_base64": base64.b64encode(img_bytes).decode("ascii"),
                    "asset_type": "bundled",
                })
            except Exception as e:
                print(f"[image_asset_collector] Warning: Could not read {info.filename} from archive: {e}")

    if assets:
        total_size = sum(a["size_bytes"] for a in assets)
        print(f"[image_asset_collector] Tableau (.twbx): collected {len(assets)} images "
              f"({total_size:,} bytes total, ~{total_size * 4 // 3:,} bytes base64)")

    return assets


def _extract_twb_thumbnails(twb_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse a .twb XML to extract only inline thumbnail images.
    Used by .twbx handler to get thumbnails from the inner .twb.
    """
    import xml.etree.ElementTree as ET

    assets: List[Dict[str, Any]] = []

    try:
        xml_text = None
        for encoding in ('utf-8', 'utf-16-le', 'utf-16-be', 'latin-1'):
            try:
                xml_text = twb_bytes.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue

        if not xml_text:
            return assets

        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return assets

    for thumbnail in root.iter('thumbnail'):
        name = thumbnail.get('name', 'unnamed')
        width = thumbnail.get('width', '0')
        height = thumbnail.get('height', '0')
        b64_data = (thumbnail.text or '').strip().replace('\n', '').replace(' ', '')

        if b64_data:
            try:
                raw_bytes = base64.b64decode(b64_data)
                size_bytes = len(raw_bytes)
            except Exception:
                size_bytes = 0

            assets.append({
                "filename": f"thumbnail_{name}.png",
                "size_bytes": size_bytes,
                "content_type": "image/png",
                "data_base64": b64_data,
                "asset_type": "thumbnail",
                "thumbnail_name": name,
                "thumbnail_width": int(width),
                "thumbnail_height": int(height),
            })

    return assets


def _collect_from_twb(twb_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract image references from a plain .twb XML file (no thumbnails)."""
    assets = _extract_twb_bitmap_refs(twb_bytes)

    if assets:
        ref_count = len(assets)
        print(f"[image_asset_collector] Tableau (.twb): collected {ref_count} external references")

    return assets


def _extract_twb_bitmap_refs(twb_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse a .twb XML to extract bitmap zone references (param attribute = local file path).
    Thumbnails are NOT extracted from .twb — only from .twbx.
    """
    import xml.etree.ElementTree as ET

    assets: List[Dict[str, Any]] = []

    # Try to parse the XML
    try:
        xml_text = None
        for encoding in ('utf-8', 'utf-16-le', 'utf-16-be', 'latin-1'):
            try:
                xml_text = twb_bytes.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue

        if not xml_text:
            return assets

        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"[image_asset_collector] Warning: XML parse error in .twb: {e}")
        return assets

    # Extract bitmap zone references (external image paths)
    seen_paths = set()
    for zone in root.iter('zone'):
        zone_type = zone.get('type-v2', zone.get('type', ''))
        if zone_type in ('bitmap', 'image'):
            param = zone.get('param', '')
            src = zone.get('src', zone.get('url', ''))
            image_ref = param or src

            if image_ref and image_ref not in seen_paths:
                seen_paths.add(image_ref)
                filename = Path(image_ref).name if image_ref else ''
                assets.append({
                    "filename": filename,
                    "source_path": image_ref,
                    "size_bytes": 0,
                    "content_type": _get_content_type(filename) if filename else "image/unknown",
                    "data_base64": None,
                    "asset_type": "external_reference",
                })

    return assets


# =============================================================================
# INTEGRATION HELPER — inject imageUrl + imageId (stored in Postgres)
# =============================================================================

def _store_image_in_postgres(report_id: str, filename: str, content_type: str, image_bytes: bytes) -> str:
    """
    Store image bytes in Postgres report_images table.
    Deduplicates: if the same filename already exists for this report, reuses the existing row.
    Returns the image_id (UUID).
    """
    import uuid
    from postgres_writer import SessionLocal
    from postgres_models import ReportImage

    session = SessionLocal()
    try:
        # Check if already stored for this report (dedup by filename + report_id)
        existing = session.query(ReportImage).filter_by(
            report_id=report_id,
            filename=filename
        ).first()

        if existing:
            return existing.image_id  # reuse existing, don't insert again

        # Insert new
        image_id = str(uuid.uuid4())
        record = ReportImage(
            image_id=image_id,
            report_id=report_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(image_bytes),
            image_data=image_bytes,
        )
        session.add(record)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[image_asset_collector] Warning: Failed to store image in Postgres: {e}")
        return ""
    finally:
        session.close()

    return image_id


def inject_inline_image_data_tableau(result: dict, file_bytes: bytes, report_id: str = "") -> None:
    """
    Inject imageUrl and imageId on each image visual.
    Stores image bytes in Postgres and puts UUID reference on the visual.
    """
    visualizations = result.get("visualizations", {})
    pages = visualizations.get("pages", []) if isinstance(visualizations, dict) else []
    if not pages:
        return

    is_twbx = zipfile.is_zipfile(io.BytesIO(file_bytes))

    # Build map: filename → raw bytes
    image_bytes_map: Dict[str, bytes] = {}
    image_content_types: Dict[str, str] = {}
    twb_bytes = file_bytes

    if is_twbx:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if _is_image_file(info.filename):
                    try:
                        img_bytes = zf.read(info.filename)
                        fname = Path(info.filename).name
                        image_bytes_map[fname] = img_bytes
                        image_bytes_map[info.filename] = img_bytes
                        image_content_types[fname] = _get_content_type(fname)
                    except Exception:
                        pass

            twb_entries = [name for name in zf.namelist() if name.lower().endswith(".twb")]
            if twb_entries:
                try:
                    twb_bytes = zf.read(twb_entries[0])
                except Exception:
                    twb_bytes = file_bytes

    zone_images_per_page = _parse_bitmap_zones_from_twb(twb_bytes)

    # In-memory dedup cache: filename → imageId
    _dedup_cache: Dict[str, str] = {}

    injected = 0
    for page in pages:
        page_name = page.get("display_name", "")
        page_zones = zone_images_per_page.get(page_name, [])
        if not page_zones:
            continue

        zones_by_id: Dict[str, dict] = {}
        zones_by_name: Dict[str, dict] = {}
        for zone in page_zones:
            zid = zone.get("zone_id", "")
            zname = zone.get("zone_name", "")
            if zid:
                zones_by_id[zid] = zone
            if zname:
                zones_by_name[zname] = zone

        for vis in page.get("visuals", []):
            if vis.get("visual_type") != "image":
                continue

            vid = str(vis.get("visual_id", ""))
            vtitle = vis.get("title", "")
            zone_info = zones_by_id.get(vid) or zones_by_name.get(vtitle)
            if not zone_info:
                continue

            filename = zone_info.get("filename", "")
            image_ref = zone_info.get("image_ref", "")
            if not vis.get("imageUrl"):
                vis["imageUrl"] = filename or image_ref

            raw_bytes = image_bytes_map.get(filename) or image_bytes_map.get(image_ref)
            if not (raw_bytes and report_id and filename):
                continue

            if filename in _dedup_cache:
                vis["imageId"] = _dedup_cache[filename]
                injected += 1
                continue

            ct = image_content_types.get(filename, _get_content_type(filename))
            image_id = _store_image_in_postgres(report_id, filename, ct, raw_bytes)
            if image_id:
                vis["imageId"] = image_id
                _dedup_cache[filename] = image_id
                injected += 1

    if injected:
        print(f"[image_asset_collector] Tableau: stored {injected} images in Postgres, injected imageId on visuals")


def _unwrap_pbi_literal(val: Any) -> str:
    """
    A Power BI config value is either a plain string or wrapped as
    {'expr': {'Literal': {'value': "'some text'"}}}. Return the plain string.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        literal = (val.get("expr", {}) or {}).get("Literal", {}) or {}
        value = literal.get("value")
        if isinstance(value, str):
            return value.strip("'\"")
    return ""


def _find_resource_item_name(node: Any) -> str:
    """
    Recursively search a Power BI visual-config subtree for a ResourcePackageItem
    and return its ItemName (the image filename in RegisteredResources/).
    """
    if isinstance(node, dict):
        rpi = node.get("ResourcePackageItem")
        if isinstance(rpi, dict):
            name = _unwrap_pbi_literal(rpi.get("ItemName"))
            if name:
                return name
        for value in node.values():
            found = _find_resource_item_name(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_resource_item_name(item)
            if found:
                return found
    return ""


def _parse_image_visuals_from_layout(layout_path: str) -> Dict[str, str]:
    """
    Parse a Power BI ``Report/Layout`` file and return {visual_id: image_filename}
    for every image visual.

    The image filename is the visual's ResourcePackageItem ItemName, which matches
    a file in ``Report/StaticResources/RegisteredResources/``. The visual_id is the
    layout container's ``name`` — the same value carried on each extracted visual
    as ``visual_id`` (before apply_readable_ids replaces it).
    """
    mapping: Dict[str, str] = {}
    path = Path(layout_path)
    if not path.is_file():
        return mapping

    # Layout is JSON, sometimes UTF-16-LE (native Power BI on-disk format).
    layout = None
    for encoding in ('utf-8', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252'):
        try:
            with open(path, 'r', encoding=encoding, errors='strict') as f:
                layout = json.loads(f.read())
            break
        except (UnicodeDecodeError, UnicodeError, ValueError):
            continue
    if not isinstance(layout, dict):
        return mapping

    for section in layout.get('sections', []):
        for vc in section.get('visualContainers', []):
            config_str = vc.get('config', '')
            if not config_str:
                continue
            try:
                config = json.loads(config_str)
            except (ValueError, TypeError):
                continue
            visual_id = config.get('name', '')
            single_visual = config.get('singleVisual', {})
            if not visual_id or not isinstance(single_visual, dict):
                continue
            if single_visual.get('visualType') != 'image':
                continue
            item_name = _find_resource_item_name(single_visual.get('objects', {}))
            if item_name:
                mapping[visual_id] = item_name

    return mapping


def inject_inline_image_data_powerbi(
    result: dict,
    pbix_extracted_dir: str,
    report_id: str = "",
    layout_path: str = "",
) -> None:
    """
    Inject imageUrl and imageId on each Power BI image visual.

    Image visuals are matched to their image file by ``visual_id``, read straight
    from the .pbix ``Report/Layout`` — no LLM involved. Image bytes are stored in
    Postgres and the UUID reference (imageId) plus resource filename (imageUrl)
    are set on the visual.

    IMPORTANT: must run BEFORE apply_readable_ids — that step drops ``visual_id``,
    which is the key used for matching here. At that point the visuals live under
    ``result["report_pages"]``; the post-transform ``visualizations.pages`` shape
    is also supported as a fallback.
    """
    # Pages: pre-transform PBIX result uses "report_pages"; post-transform uses
    # "visualizations": {"pages": [...]}.
    pages = result.get("report_pages")
    if pages is None:
        visualizations = result.get("visualizations", {})
        pages = visualizations.get("pages", []) if isinstance(visualizations, dict) else []
    if not pages:
        return

    base_dir = Path(pbix_extracted_dir)

    # 1. Collect image files bundled in the extracted .pbix resource folders.
    image_bytes_map: Dict[str, bytes] = {}
    image_content_types: Dict[str, str] = {}
    resource_dirs = [
        base_dir / "Report" / "StaticResources" / "RegisteredResources",
        base_dir / "Report" / "StaticResources",
    ]
    for resource_dir in resource_dirs:
        if not resource_dir.exists():
            continue
        for file_path in resource_dir.iterdir():
            if file_path.is_file() and _is_image_file(file_path.name):
                try:
                    image_bytes_map[file_path.name] = file_path.read_bytes()
                    image_content_types[file_path.name] = _get_content_type(file_path.name)
                except Exception:
                    pass

    if not image_bytes_map:
        return

    # 2. Map visual_id -> image filename straight from Report/Layout.
    if not layout_path:
        layout_path = str(base_dir / "Report" / "Layout")
    layout_image_map = _parse_image_visuals_from_layout(layout_path)

    # In-memory dedup cache: filename -> imageId (avoids duplicate Postgres inserts).
    _dedup_cache: Dict[str, str] = {}

    def _store(filename: str) -> str:
        if filename in _dedup_cache:
            return _dedup_cache[filename]
        ct = image_content_types.get(filename, _get_content_type(filename))
        image_id = _store_image_in_postgres(report_id, filename, ct, image_bytes_map[filename])
        if image_id:
            _dedup_cache[filename] = image_id
        return image_id

    injected = 0
    for page in pages:
        for vis in page.get("visuals", []):
            if vis.get("visual_type") != "image":
                continue

            vid = str(vis.get("visual_id", ""))
            filename = layout_image_map.get(vid, "")

            # Fallback: exactly one image in the report and no explicit match.
            if not filename and len(image_bytes_map) == 1:
                filename = next(iter(image_bytes_map))

            if not filename or filename not in image_bytes_map:
                continue

            vis["imageUrl"] = filename
            if report_id:
                image_id = _store(filename)
                if image_id:
                    vis["imageId"] = image_id
                    injected += 1

    if injected:
        print(f"[image_asset_collector] Power BI: stored {injected} images in Postgres, injected imageId on visuals")


def _parse_bitmap_zones_from_twb(twb_bytes: bytes) -> Dict[str, list]:
    """
    Parse .twb XML and return bitmap zones grouped by dashboard name.

    Returns:
        Dict mapping dashboard_name → list of zone info dicts (ordered by appearance):
        [{"image_ref": "Image/bg.jfif", "filename": "bg.jfif"}, ...]
    """
    import xml.etree.ElementTree as ET

    result: Dict[str, list] = {}

    try:
        xml_text = None
        for encoding in ('utf-8', 'utf-16-le', 'utf-16-be', 'latin-1'):
            try:
                xml_text = twb_bytes.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue

        if not xml_text:
            return result

        root = ET.fromstring(xml_text)
    except Exception:
        return result

    # Find all dashboards and their bitmap zones
    for dashboard in root.iter('dashboard'):
        dash_name = dashboard.get('name', '')
        zones_info = []

        # Iterate all zones in document order
        for zone in dashboard.iter('zone'):
            zone_type = zone.get('type-v2', zone.get('type', ''))
            if zone_type in ('bitmap', 'image'):
                param = zone.get('param', '')
                src = zone.get('src', zone.get('url', ''))
                image_ref = param or src
                filename = Path(image_ref).name if image_ref else ''
                zones_info.append({
                    "zone_id": zone.get('id', ''),
                    "zone_name": zone.get('name', ''),
                    "image_ref": image_ref,
                    "filename": filename,
                })

        if zones_info:
            result[dash_name] = zones_info

    return result


# =============================================================================
# STANDALONE TEST — run this file directly to test with an extracted PBIX
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python image_asset_collector.py <extracted_pbix_dir>")
        print("  python image_asset_collector.py <file.twbx>")
        sys.exit(1)

    target = sys.argv[1]
    target_path = Path(target)

    if target_path.is_dir():
        # Power BI extracted directory
        print(f"Scanning Power BI extracted directory: {target_path}")
        assets = collect_powerbi_image_assets(str(target_path))
    elif target_path.is_file() and target_path.suffix.lower() == ".twbx":
        # Tableau .twbx file
        print(f"Scanning Tableau .twbx file: {target_path}")
        assets = collect_tableau_image_assets(target_path.read_bytes())
    elif target_path.is_file() and target_path.suffix.lower() == ".twb":
        # Tableau .twb file
        print(f"Scanning Tableau .twb file: {target_path}")
        assets = collect_tableau_image_assets(target_path.read_bytes())
    else:
        print(f"ERROR: '{target}' is not a directory, .twb, or .twbx file")
        sys.exit(1)

    if not assets:
        print("No image assets found.")
        sys.exit(0)

    # Print summary (without full base64 data)
    print(f"\nFound {len(assets)} image(s):\n")
    for i, asset in enumerate(assets, 1):
        b64_data = asset.get("data_base64") or ""
        b64_preview = b64_data[:40] + "..." if len(b64_data) > 40 else (b64_data or "(not available - external reference)")
        print(f"  {i}. {asset['filename']}")
        print(f"     Path: {asset.get('relative_path') or asset.get('archive_path') or asset.get('source_path')}")
        print(f"     Size: {asset['size_bytes']:,} bytes")
        print(f"     Type: {asset['content_type']}")
        print(f"     Asset type: {asset.get('asset_type', 'unknown')}")
        print(f"     Base64 preview: {b64_preview}")
        print()

    # Optionally write full JSON to file
    if len(sys.argv) > 2 and sys.argv[2] == "--json":
        out_path = target_path.parent / "image_assets_output.json" if target_path.is_file() else target_path / "image_assets_output.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"image_assets": assets}, f, indent=2)
        print(f"Full JSON written to: {out_path}")
