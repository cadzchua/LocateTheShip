import os
import psycopg2
import folium
import random, math
from collections import defaultdict
from datetime import datetime

DATA_STORE_HOST = os.environ.get("DATA_STORE_HOST", "localhost")
DATA_STORE_PORT = os.environ.get("DATA_STORE_PORT", "5432")
DATA_STORE_DATABASE = os.environ.get("DATA_STORE_DATABASE", "postgres")
DATA_STORE_USER = os.environ.get("DATA_STORE_USER", "sa")
DATA_STORE_PASSWORD = os.environ.get("DATA_STORE_PASSWORD", "YourStrongPassword123")
DATA_STORE_TABLE = os.environ.get("DATA_STORE_TABLE", "aisstream_combined")

def query():
    """
    Generates SQL query.
    """
    FILTER_MMSI = [] # List of integers
    FILTER_SHIP_NAME = [] # List of strings
    FILTER_TIME_RANGE = [] # List of tuples (start, end) example: ('2024-03-26 13:07:00', '2024-03-26 13:23:00')

    mmsi_condition = " OR ".join([f""""AIS_MMSI" = '{mmsi}'""" for mmsi in FILTER_MMSI])
    ship_name_condition = " OR ".join([f"""TRIM("AIS_SHIP_NAME") ILIKE '{name}'""" for name in FILTER_SHIP_NAME])  # Trim to remove trailing whitespace and ILIKE for case-insensitive comparison.(= for case-sensitive comparison)
    time_range_condition = " AND ".join([f""""AIS_TIME" >= '{start}' AND "AIS_TIME" <= '{end}'""" for start, end in FILTER_TIME_RANGE])

    # Construct the SQL query with the filters
    sql_query = f"SELECT * FROM {DATA_STORE_TABLE} WHERE "
    conditions1 = []
    conditions2 = []
    if mmsi_condition:
        conditions1.append(mmsi_condition)
    if ship_name_condition:
        conditions1.append(ship_name_condition)
    if time_range_condition:
        conditions2.append(time_range_condition)

    if conditions1 and conditions2: 
        sql_query += " OR ".join(conditions1) + " AND " + " AND ".join(conditions2)             
    elif conditions1:
        sql_query += " OR ".join(conditions1)
    elif conditions2:
        sql_query += " AND ".join(conditions2)
    else:
        # If no filters are applied, retrieve all records
        sql_query += "1=1;"
    return sql_query

def connect_to_postgres():
    """
    Establishes a connection to the PostgreSQL database.
    """
    conn = psycopg2.connect(
        host=DATA_STORE_HOST,
        port=DATA_STORE_PORT,
        database=DATA_STORE_DATABASE,
        user=DATA_STORE_USER,
        password=DATA_STORE_PASSWORD,
    )
    return conn

def execute_sql_query(sql):
    """
    Executes SQL query.
    """
    conn = connect_to_postgres()
    cursor = conn.cursor()
    cursor.execute(sql)
    result = cursor.fetchall()
    conn.close()  
    return result

def generate_random_color():
    """
    Generate a random color in hex format.
    """
    r = lambda: random.randint(0, 255)
    return '#{:02x}{:02x}{:02x}'.format(r(), r(), r())

def calculate_bearing(point1, point2):
    """ 
    Calculates the bearing given two points.
    """
    lon1, lat1 = point1
    lon2, lat2 = point2
    delta_lon = math.radians(lon2 - lon1)
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon))
    initial_bearing = math.atan2(x, y)
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360

    return compass_bearing

if __name__ == "__main__":
    sql_query = query()
    query_result = execute_sql_query(sql_query)
    ship_icon_path = 'application/ship.png'
    if query_result:
        mymap = folium.Map(location=[query_result[0][2], query_result[0][3]], zoom_start=10)
    else:
        mymap = folium.Map()
    prev_points = defaultdict(list)
    mmsi_colors = {}  # Track colors for each MMSI
    
    ship_group = folium.FeatureGroup()

    for idx, row in enumerate(query_result):
        ship_name, mmsi, lat, lon, time_str = row
        time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')

        # Create ship icon marker
        ship_icon = folium.features.CustomIcon(ship_icon_path, icon_size=(20, 20))
        marker = folium.Marker([lat, lon], popup=ship_name, icon=ship_icon)
        mymap.add_child(marker)

        prev_mmsi_points = prev_points[mmsi]
        if prev_mmsi_points:
            prev_lon, prev_lat, prev_time = prev_mmsi_points[-1]
            
            # Check if there are any intermediate points
            intermediate_points = any(point[2] > prev_time and point[2] < time for point in prev_mmsi_points)
            
            if not intermediate_points:
                # Determine color for the current MMSI
                if mmsi not in mmsi_colors:
                    mmsi_colors[mmsi] = generate_random_color()
                color = mmsi_colors[mmsi]
                
                # Draw line between previous point and current point using the same color
                line = folium.PolyLine(locations=[[prev_lat, prev_lon], [lat, lon]], color=color)
                mymap.add_child(line)

                # Calculate bearing between two consecutive points
                bearing = calculate_bearing((prev_lon, prev_lat), (lon, lat))

                # Add arrow marker at the end of the line using a regular polygon marker
                arrow = folium.RegularPolygonMarker(location=((lat + prev_lat) / 2, (lon + prev_lon) / 2), color=color, fill_color=color, weight=6, number_of_sides=3, radius=7, rotation=bearing - 90)
                mymap.add_child(arrow)

        prev_points[mmsi].append((lon, lat, time))
    # Save the map to an HTML file
    mymap.save('application/path_map.html')
