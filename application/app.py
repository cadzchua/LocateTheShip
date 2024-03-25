import os
import psycopg2
import folium
import random
from folium.plugins import TimestampedGeoJson

DATA_STORE_HOST = os.environ.get("DATA_STORE_HOST", "localhost")
DATA_STORE_PORT = os.environ.get("DATA_STORE_PORT", "5432")
DATA_STORE_DATABASE = os.environ.get("DATA_STORE_DATABASE", "postgres")
DATA_STORE_USER = os.environ.get("DATA_STORE_USER", "sa")
DATA_STORE_PASSWORD = os.environ.get("DATA_STORE_PASSWORD", "YourStrongPassword123")
DATA_STORE_TABLE = os.environ.get("DATA_STORE_TABLE", "aisstream_combined")

def connect_to_postgres():
    """Establishes a connection to the PostgreSQL database."""
    conn = psycopg2.connect(
        host=DATA_STORE_HOST,
        port=DATA_STORE_PORT,
        database=DATA_STORE_DATABASE,
        user=DATA_STORE_USER,
        password=DATA_STORE_PASSWORD,
    )
    return conn

def execute_sql_query(sql):
    """Executes SQL query."""
    conn = connect_to_postgres()
    cursor = conn.cursor()
    cursor.execute(sql)
    result = cursor.fetchall()
    conn.close()  # Close connection after fetching results
    return result

def generate_random_color():
    """Generate a random color in hex format."""
    r = lambda: random.randint(0, 255)
    return '#{:02x}{:02x}{:02x}'.format(r(), r(), r())

if __name__ == "__main__":
    # Example query to select ship name, latitude, longitude, and time
    sql_query = f"SELECT * FROM {DATA_STORE_TABLE};"
    query_result = execute_sql_query(sql_query)

    # Create a Folium map centered at the first data point
    m = folium.Map(location=[query_result[0][2], query_result[0][3]], zoom_start=10)

    # Create a feature group for lines
    line_group = folium.FeatureGroup(name="Lines")
    m.add_child(line_group)

    # Create a list to store GeoJSON features
    features = []

    # Initialize previous point
    prev_point = None

    # Define custom icon properties
    icon_image = 'application/ship.png'  # Path to your custom ship icon image
    icon = folium.CustomIcon(
        icon_image,
        icon_size=(38, 95),
        icon_anchor=(22, 94)
    )

    # Iterate over query results to create features
    for row in query_result:
        ship_name, mmsi, lat, lon, time = row

        # Create point feature with custom icon
        point_feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"time": time, "popup": ship_name},
            "icon": icon
        }

        # Create line feature
        if prev_point is not None:
            line_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [prev_point[0], prev_point[1]],
                        [lon, lat]
                    ]
                },
                "properties": {"time": time, "popup": ship_name, "style": {"color": generate_random_color()}, "icon": icon}
            }
            features.append(line_feature)

        # Update previous point
        prev_point = [lon, lat]

        # Append point feature
        features.append(point_feature)

    # Add TimestampedGeoJson to the map
    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features},
        period="PT30M",
        add_last_point=True,
        auto_play=False,
        loop=False,
        max_speed=1,
        loop_button=True,
        date_options="YYYY-MM-DD",
        time_slider_drag_update=True,
    ).add_to(m)

    # Save the map to an HTML file
    m.save("application/map_with_timeline.html")
