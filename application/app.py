from flask import Flask
from flask import render_template, request, redirect, url_for
import folium, colorsys, hashlib, os, psycopg2, branca
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)

DATA_STORE_HOST = os.environ.get("DATA_STORE_HOST", "localhost")
DATA_STORE_PORT = os.environ.get("DATA_STORE_PORT", "5432")
DATA_STORE_DATABASE = os.environ.get("DATA_STORE_DATABASE", "postgres")
DATA_STORE_USER = os.environ.get("DATA_STORE_USER", "sa")
DATA_STORE_PASSWORD = os.environ.get("DATA_STORE_PASSWORD", "YourStrongPassword123")
DATA_STORE_TABLE = os.environ.get("DATA_STORE_TABLE", "aisstream_combined")

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

SOG_NOT_AVAILABLE = 102.3
COG_NOT_AVAILABLE = 360.0
HEADING_NOT_AVAILABLE = 511


def build_query(shipnames, mmsis, startdate, enddate, source):
    """
    Builds a parameterized SQL query. Ship name and MMSI filters are ORed
    together (match any of the requested ships), then ANDed with the time
    range and source filters.
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
    sql = f'SELECT {COLUMN_SQL} FROM {DATA_STORE_TABLE} WHERE {where} ORDER BY "AIS_TIME" ASC'
    return sql, params


def connect_to_postgres():
    """
    Establishes a connection to the PostgreSQL database.
    """
    return psycopg2.connect(
        host=DATA_STORE_HOST,
        port=DATA_STORE_PORT,
        database=DATA_STORE_DATABASE,
        user=DATA_STORE_USER,
        password=DATA_STORE_PASSWORD,
    )


def execute_sql_query(sql, params=None):
    """
    Executes SQL query and returns all rows.
    """
    conn = connect_to_postgres()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or [])
        return cursor.fetchall()
    finally:
        conn.close()


def fetch_sources():
    """
    Distinct data sources present in the table, for the filter dropdown.
    """
    try:
        rows = execute_sql_query(f'SELECT DISTINCT "AIS_SOURCE" FROM {DATA_STORE_TABLE}')
        return sorted(row[0] for row in rows if row[0])
    except psycopg2.Error:
        return []


def color_for_mmsi(mmsi):
    """
    Deterministic per-ship color, stable across page refreshes so analysts
    can visually re-identify a track after filtering or reloading.
    """
    hue = int(hashlib.md5(str(mmsi).encode()).hexdigest(), 16) % 360
    r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.42, 0.75)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def fmt_sog(sog):
    if sog is None or sog >= SOG_NOT_AVAILABLE:
        return "N/A"
    return f"{sog:.1f} kn"


def fmt_cog(cog):
    if cog is None or cog >= COG_NOT_AVAILABLE:
        return "N/A"
    return f"{cog:.1f}°"


def fmt_heading(heading):
    if heading is None or heading == HEADING_NOT_AVAILABLE:
        return "N/A"
    return f"{heading}°"


def fmt_nav_status(nav_status):
    if nav_status is None:
        return "N/A"
    return NAV_STATUS_LABELS.get(nav_status, f"Code {nav_status}")


def rotation_for(point):
    """
    Best available bearing for the ship icon: true heading when the
    transponder reports one, otherwise course over ground, otherwise none.
    """
    heading, cog = point["heading"], point["cog"]
    if heading is not None and 0 <= heading < HEADING_NOT_AVAILABLE:
        return heading
    if cog is not None and 0 <= cog < COG_NOT_AVAILABLE:
        return cog
    return None


def ship_icon_html(color, rotation):
    """
    A small (18px) directional vessel marker. Kept deliberately compact so
    dense traffic areas stay readable; the ship name lives in the hover
    tooltip instead of a permanent label.
    """
    rot = rotation if rotation is not None else 0
    return f"""
    <div style="transform: rotate({rot}deg); width:18px; height:18px;">
      <svg viewBox="0 0 24 24" width="18" height="18">
        <path d="M12 1 L19 21 L12 16.5 L5 21 Z" fill="{color}" stroke="#1f2937" stroke-width="1.5" stroke-linejoin="round"/>
      </svg>
    </div>
    """


def popup_for(point):
    html = f"""
    <div style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1.5;">
        <h3 style="margin: 0 0 6px 0;">{point['ship_name'].strip() or 'Unknown vessel'}</h3>
        <strong>MMSI:</strong> {point['mmsi']}<br/>
        <strong>Time:</strong> {point['time_str']}<br/>
        <strong>Position:</strong> {point['lat']:.5f}, {point['lon']:.5f}<br/>
        <strong>Speed (SOG):</strong> {fmt_sog(point['sog'])}<br/>
        <strong>Course (COG):</strong> {fmt_cog(point['cog'])}<br/>
        <strong>Heading:</strong> {fmt_heading(point['heading'])}<br/>
        <strong>Nav status:</strong> {fmt_nav_status(point['nav_status'])}<br/>
        <strong>Source:</strong> {point['source'] or 'unknown'}
    </div>
    """
    iframe = branca.element.IFrame(html=html, width=300, height=230)
    return folium.Popup(iframe)


def parse_rows(query_result):
    """
    Groups raw rows into per-ship tracks ordered by time.
    """
    tracks = defaultdict(list)
    for row in query_result:
        ship_name, mmsi, lat, lon, time_str, sog, cog, heading, nav_status, source = row
        try:
            time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            continue
        tracks[mmsi].append({
            "ship_name": ship_name or "",
            "mmsi": mmsi,
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
    for points in tracks.values():
        points.sort(key=lambda p: p["time"])
    return tracks


def map_plot(query_result):
    """
    Plots ship tracks on a map. The latest position of each ship gets a
    directional icon; older positions are small dots along the track line.
    Returns (map_html, stats).
    """
    tracks = parse_rows(query_result)
    stats = {
        "ships": len(tracks),
        "points": sum(len(points) for points in tracks.values()),
        "start": None,
        "end": None,
    }
    if not tracks:
        return None, stats

    all_times = [p["time"] for points in tracks.values() for p in points]
    stats["start"] = min(all_times).strftime("%Y-%m-%d %H:%M:%S")
    stats["end"] = max(all_times).strftime("%Y-%m-%d %H:%M:%S")

    lats = [p["lat"] for points in tracks.values() for p in points]
    lons = [p["lon"] for points in tracks.values() for p in points]
    map = folium.Map(location=[sum(lats) / len(lats), sum(lons) / len(lons)], zoom_start=10)
    if len(lats) > 1:
        map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30))

    for mmsi, points in tracks.items():
        color = color_for_mmsi(mmsi)
        latest = points[-1]
        display_name = latest["ship_name"].strip() or str(mmsi)

        if len(points) > 1:
            line = folium.PolyLine(
                locations=[[p["lat"], p["lon"]] for p in points],
                color=color,
                weight=2,
                opacity=0.8,
            )
            map.add_child(line)

        for point in points[:-1]:
            dot = folium.CircleMarker(
                location=[point["lat"], point["lon"]],
                radius=3,
                color=color,
                fill=True,
                fill_opacity=0.9,
                weight=1,
                tooltip=f"{display_name} • {point['time_str']} • {fmt_sog(point['sog'])}",
            )
            map.add_child(dot)

        marker = folium.Marker(
            [latest["lat"], latest["lon"]],
            icon=folium.DivIcon(
                html=ship_icon_html(color, rotation_for(latest)),
                icon_size=(18, 18),
                icon_anchor=(9, 9),
            ),
            tooltip=f"{display_name} • {fmt_sog(latest['sog'])} • {latest['time_str']}",
            popup=popup_for(latest),
        )
        map.add_child(marker)

    return map._repr_html_(), stats


def render_map_page(query_result, warning=None):
    map_html, stats = map_plot(query_result)
    return render_template(
        "index.html",
        map_html=map_html,
        stats=stats,
        warning=warning,
        sources=fetch_sources(),
    )


@app.route('/')
def home():
    """
    Home Screen
    """
    return render_template('home.html')


@app.route('/map', methods=['GET', 'POST'])
def map():
    """
    Loads an initial map with all the ships in DB
    """
    if request.method == 'POST':
        return redirect(url_for('map'))
    sql, params = build_query([], [], "", "", "")
    try:
        query_result = execute_sql_query(sql, params)
        warning = None
    except psycopg2.Error:
        # Table does not exist yet or DB is unreachable: the pipeline is
        # still warming up on first start, so show a friendly page that
        # retries instead of a stack trace.
        query_result = []
        warning = "The data pipeline is still warming up (no data yet). This page retries automatically."
    return render_map_page(query_result, warning)


@app.route('/filter', methods=['GET', 'POST'])
def filter_data():
    """
    Loads a map based on the user's query.
    """
    if request.method == 'GET':
        return redirect(url_for('map'))

    shipnames = [name.strip() for name in request.form.get('shipNames', '').split(",") if name.strip()]
    mmsis = []
    for token in request.form.get('mmsi', '').split(","):
        token = token.strip()
        if token:
            try:
                mmsis.append(int(token))
            except ValueError:
                pass
    start_datetime = request.form.get('timeRange1', '').replace('T', ' ')
    end_datetime = request.form.get('timeRange2', '').replace('T', ' ')
    source = request.form.get('source', '').strip()

    sql, params = build_query(shipnames, mmsis, start_datetime, end_datetime, source)
    try:
        query_result = execute_sql_query(sql, params)
        warning = None
    except psycopg2.Error:
        query_result = []
        warning = "The data pipeline is still warming up (no data yet). This page retries automatically."
    return render_map_page(query_result, warning)


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
