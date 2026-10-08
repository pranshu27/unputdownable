"""
image_store.py — Fetch report-image binaries from Postgres.

Image visuals in the extraction JSON carry an `imageId` (a UUID) and an
`imageUrl` (the original filename). The actual image bytes live in Postgres:

    SELECT image_data, filename, content_type
    FROM   jnj_poc.report_images
    WHERE  image_id = '<uuid>';

`image_data` is a `bytea` column. This module looks the rows up by id and
returns the decoded bytes so the PBIP writer can drop them into the report's
StaticResources/RegisteredResources/ folder.

Connection: `POSTGRES_URL` from the environment (.env), e.g.
    postgresql://user:pwd@host:5432/db?sslmode=require

All failures (no URL, connection refused, missing rows) are non-fatal — the
caller treats a missing image the same as "no image", so a Postgres outage
never blocks a conversion.
"""
import os

try:
    import psycopg2
except ImportError:                       # pragma: no cover - dependency guard
    psycopg2 = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:                       # pragma: no cover
    pass


def fetch_images(image_ids) -> dict[str, dict]:
    """Look up image binaries by id.

    Parameters
    ----------
    image_ids : iterable of str — `image_id` values from the JSON's image
                visuals.

    Returns
    -------
    dict mapping `image_id` -> {"filename", "content_type", "asset_role",
    "data" (bytes)}. Ids that are missing / unreachable are simply absent.
    `asset_role` is a coarse hint (image_visual | page_background |
    page_wallpaper | shape_fill | report_wallpaper | multiple | unreferenced)
    and may be None on rows written before that column existed.
    """
    ids = sorted({str(i).strip() for i in image_ids if i})
    if not ids:
        return {}

    url = os.environ.get("POSTGRES_URL")
    if not url or psycopg2 is None:
        return {}

    out: dict[str, dict] = {}
    conn = None
    try:
        conn = psycopg2.connect(url, connect_timeout=15)
        with conn.cursor() as cur:
            # `asset_role` was added later; COALESCE-free SELECT is fine since
            # the column is nullable — older rows just return None for it.
            cur.execute(
                "SELECT image_id, filename, content_type, asset_role, image_data "
                "FROM jnj_poc.report_images WHERE image_id = ANY(%s)",
                (ids,),
            )
            for image_id, filename, content_type, asset_role, data in cur.fetchall():
                if data is None:
                    continue
                out[str(image_id)] = {
                    "filename":     filename or f"{image_id}.png",
                    "content_type": content_type or "image/png",
                    "asset_role":   asset_role,
                    "data":         bytes(data),   # bytea → memoryview → bytes
                }
    except Exception:
        # Non-fatal: a Postgres outage must not block a conversion.
        return out
    finally:
        if conn is not None:
            conn.close()
    return out
