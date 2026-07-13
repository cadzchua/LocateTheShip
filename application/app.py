from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
import colorsys, csv, hashlib, io, os, psycopg2
from collections import defaultdict
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

DATA_STORE_HOST = os.environ.get("DATA_STORE_HOST", "localhost")
DATA_STORE_PORT = os.environ.get("DATA_STORE_PORT", "5432")
DATA_STORE_DATABASE = os.environ.get("DATA_STORE_DATABASE", "postgres")
DATA_STORE_USER = os.environ.get("DATA_STORE_USER", "sa")
DATA_STORE_PASSWORD = os.environ.get("DATA_STORE_PASSWORD", "YourStrongPassword123")
DATA_STORE_TABLE = os.environ.get("DATA_STORE_TABLE", "aisstream_combined")

# Hard cap on rows returned per query so one huge time window cannot stall
# the API; newest rows win and the response flags truncation.
MAX_ROWS = int(os.environ.get("MAX_QUERY_ROWS", "20000"))

COLUMNS = [
    "AIS_SHIP_NAME",
    "AIS_MMSI",
    "AIS_LATITUDE",
    "AIS_LONGITUDE",
    "AIS_TIME",
    "AIS_SOG",
    "AIS_COG",
    "AIS_HEADING",
    "AIS_NAV_STATUS",
    "AIS_SOURCE",
]
COLUMN_SQL = ", ".join(f'"{col}"' for col in COLUMNS)

# ITU-R M.1371 navigational status codes
NAV_STATUS_LABELS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    11: "Towing astern",
    12: "Pushing ahead / towing alongside",
    14: "AIS-SART / MOB / EPIRB",
    15: "Undefined",
}

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def utc8_now():
    """The pipeline stores naive UTC+8 timestamps; compare in the same frame."""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).replace(tzinfo=None)


def build_query(shipnames, mmsis, startdate, enddate, source):
    """
    Builds a parameterized SQL query. Ship name and MMSI filters are ORed
    together (match any of the requested ships), then ANDed with the time
    range and source filters. Newest rows first, capped at MAX_ROWS.
    """
    conditions, params = [], []

    identity = []
    for name in shipnames:
        identity.append('TRIM("AIS_SHIP_NAME") ILIKE %s')
        params.append(name)
    for mmsi in mmsis:
        identity.append('"AIS_MMSI" = %s')
        params.append(mmsi)
    if identity:
        conditions.append("(" + " OR ".join(identity) + ")")

    if startdate:
        conditions.append('"AIS_TIME" >= %s')
        params.append(startdate)
    if enddate:
        conditions.append('"AIS_TIME" <= %s')
        params.append(enddate)
    if source:
        conditions.append('"AIS_SOURCE" = %s')
        params.append(source)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = (
        f'SELECT {COLUMN_SQL} FROM {DATA_STORE_TABLE} WHERE {where} '
        f'ORDER BY "AIS_TIME" DESC LIMIT %s'
    )
    params.append(MAX_ROWS)
    return sql, params


def connect_to_postgres():
    return psycopg2.connect(
        host=DATA_STORE_HOST,
        port=DATA_STORE_PORT,
        database=DATA_STORE_DATABASE,
        user=DATA_STORE_USER,
        password=DATA_STORE_PASSWORD,
    )


def execute_sql_query(sql, params=None):
    conn = connect_to_postgres()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or [])
        return cursor.fetchall()
    finally:
        conn.close()


def fetch_sources():
    rows = execute_sql_query(f'SELECT DISTINCT "AIS_SOURCE" FROM {DATA_STORE_TABLE}')
    return sorted(row[0] for row in rows if row[0])


def color_for_mmsi(mmsi):
    """
    Deterministic per-vessel color, stable across refreshes so analysts can
    visually re-identify a track. Lightness/chroma chosen to stay readable
    on both the dark and light map tiles.
    """
    hue = int(hashlib.md5(str(mmsi).encode()).hexdigest(), 16) % 360
    r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.58, 0.72)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def parse_filters(args):
    """
    Reads the shared filter parameters from a request's query string.
    """
    shipnames = [s.strip() for s in args.get("ship_names", "").split(",") if s.strip()]
    mmsis = []
    for token in args.get("mmsi", "").split(","):
        token = token.strip()
        if token:
            try:
                mmsis.append(int(token))
            except ValueError:
                pass
    start = args.get("start", "").replace("T", " ").strip()
    end = args.get("end", "").replace("T", " ").strip()
    source = args.get("source", "").strip()
    return shipnames, mmsis, start, end, source


def rows_to_vessels(rows):
    """
    Groups raw rows (newest first) into per-vessel tracks ordered oldest to
    newest, plus summary stats for the KPI header.
    """
    now = utc8_now()
    grouped = defaultdict(list)
    for row in rows:
        ship_name, mmsi, lat, lon, time_str, sog, cog, heading, nav_status, source = row
        try:
            time = datetime.strptime(time_str, TIME_FORMAT)
        except (TypeError, ValueError):
            continue
        grouped[mmsi].append({
            "name": (ship_name or "").strip(),
            "lat": lat,
            "lon": lon,
            "time": time,
            "time_str": time_str,
            "sog": sog,
            "cog": cog,
            "heading": heading,
            "nav_status": nav_status,
            "source": source,
        })

    vessels = []
    all_times = []
    for mmsi, points in grouped.items():
        points.sort(key=lambda p: p["time"])
        all_times.append(points[0]["time"])
        all_times.append(points[-1]["time"])
        latest = points[-1]
        vessels.append({
            "mmsi": mmsi,
            "name": latest["name"] or str(mmsi),
            "color": color_for_mmsi(mmsi),
            "reports": len(points),
            "first_seen": points[0]["time_str"],
            "latest": {
                "lat": latest["lat"],
                "lon": latest["lon"],
                "time": latest["time_str"],
                "age_seconds": max(0, int((now - latest["time"]).total_seconds())),
                "sog": latest["sog"],
                "cog": latest["cog"],
                "heading": latest["heading"],
                "nav_status": latest["nav_status"],
                "nav_text": NAV_STATUS_LABELS.get(latest["nav_status"], f"Code {latest['nav_status']}"),
                "source": latest["source"],
            },
            "track": [
                {"lat": p["lat"], "lon": p["lon"], "time": p["time_str"], "sog": p["sog"]}
                for p in points
            ],
        })

    stats = {
        "vessels": len(vessels),
        "reports": sum(v["reports"] for v in vessels),
        "start": min(all_times).strftime(TIME_FORMAT) if all_times else None,
        "end": max(all_times).strftime(TIME_FORMAT) if all_times else None,
        "truncated": len(rows) >= MAX_ROWS,
    }
    return vessels, stats


@app.route("/")
def console():
    """The analyst console (single page app)."""
    return render_template("console.html")


@app.route("/map", methods=["GET", "POST"])
def legacy_map():
    """Old entry point kept as a redirect so bookmarks still work."""
    return redirect(url_for("console"))


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/api/vessels")
def api_vessels():
    """
    Filtered vessel positions grouped per ship, for the console frontend.
    While the pipeline is still bootstrapping (table missing / DB down) the
    response carries warming_up=true instead of an error.
    """
    shipnames, mmsis, start, end, source = parse_filters(request.args)
    sql, params = build_query(shipnames, mmsis, start, end, source)
    try:
        rows = execute_sql_query(sql, params)
        sources = fetch_sources()
        warming_up = False
    except psycopg2.Error:
        rows, sources, warming_up = [], [], True

    vessels, stats = rows_to_vessels(rows)
    return jsonify({
        "ok": True,
        "warming_up": warming_up,
        "generated_at": utc8_now().strftime(TIME_FORMAT),
        "sources": sources,
        "stats": stats,
        "vessels": vessels,
    })


@app.route("/api/export.csv")
def api_export_csv():
    """
    CSV download of the currently filtered raw reports, for offline analysis.
    """
    shipnames, mmsis, start, end, source = parse_filters(request.args)
    sql, params = build_query(shipnames, mmsis, start, end, source)
    try:
        rows = execute_sql_query(sql, params)
    except psycopg2.Error:
        rows = []

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ship_name", "mmsi", "latitude", "longitude", "time",
                     "sog_knots", "cog_deg", "heading_deg", "nav_status", "nav_status_text", "source"])
    for row in rows:
        ship_name, mmsi, lat, lon, time_str, sog, cog, heading, nav_status, src = row
        writer.writerow([
            (ship_name or "").strip(), mmsi, lat, lon, time_str, sog, cog, heading,
            nav_status, NAV_STATUS_LABELS.get(nav_status, f"Code {nav_status}"), src,
        ])

    filename = "aisstream_export_" + utc8_now().strftime("%Y%m%d_%H%M%S") + ".csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    # Debug (and the Werkzeug debugger it enables) must be opted into
    # explicitly; never run it by default in a deployed container.
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", debug=debug)
