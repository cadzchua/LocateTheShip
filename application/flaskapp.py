from flask import Flask
from flask import render_template, request, redirect, url_for
import os
import psycopg2
import folium
import random
import math
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)

prev_points = defaultdict(list)
mmsi_colors = {}  # Track colors for each MMSI

DATA_STORE_HOST = os.environ.get("DATA_STORE_HOST", "localhost")
DATA_STORE_PORT = os.environ.get("DATA_STORE_PORT", "5432")
DATA_STORE_DATABASE = os.environ.get("DATA_STORE_DATABASE", "postgres")
DATA_STORE_USER = os.environ.get("DATA_STORE_USER", "sa")
DATA_STORE_PASSWORD = os.environ.get("DATA_STORE_PASSWORD", "YourStrongPassword123")
DATA_STORE_TABLE = os.environ.get("DATA_STORE_TABLE", "aisstream_combined")

def query(shipname: list, mmsi: list, startdate: str, enddate: str):
    """
    Generates SQL query with optional filters.
    """
    ship_name_condition, mmsi_condition, time_range_condition = "", "", ""
    if shipname != ['']:
        ship_name_condition = " OR ".join([f"""TRIM("AIS_SHIP_NAME") ILIKE '{name}'""" for name in shipname])
    if mmsi != ['']:
        mmsi_condition = " OR ".join([f""""AIS_MMSI" = '{mmsi}'""" for mmsi in mmsi])

    # Construct the SQL query with the filters
    sql_query = f"SELECT * FROM {DATA_STORE_TABLE} WHERE "
    conditions1 = []
    conditions2 = []
    if mmsi_condition:
        conditions1.append(mmsi_condition)
    if ship_name_condition:
        conditions1.append(ship_name_condition)
    if startdate:
        conditions2.append(f'"AIS_TIME" >= \'{startdate}\'')
    if enddate:
        conditions2.append(f'"AIS_TIME" <= \'{enddate}\'')

    if conditions1 and conditions2: 
        sql_query += " OR ".join(conditions1) + " AND " + " AND ".join(conditions2)             
    elif conditions1:
        sql_query += " OR ".join(conditions1)
    elif conditions2:
        sql_query += " AND ".join(conditions2)
    else:
        # If no filters are applied, retrieve all records
        sql_query += "1=1;"
    print(sql_query)
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

def map_plot(query_result):
    prev_points.clear()
    if not query_result:
        return "There is no ship!"
    
    map = folium.Map(location=[query_result[0][2], query_result[0][3]], zoom_start=10)

    for _, row in enumerate(query_result):
        ship_name, mmsi, lat, lon, time_str = row
        time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        # Create ship icon marker
        ship_icon_path = "static/images/ship.png"
        ship_icon_with_name_html = f"""
        <div style="position:relative; text-align:center;">
            <img src="{ship_icon_path}" style="width:30px; height:30px;">
            <div>{ship_name.strip()}</div>
        </div>
        """

        marker = folium.Marker([lat, lon], icon=folium.DivIcon(html=ship_icon_with_name_html))
        map.add_child(marker)
        
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
                map.add_child(line)

                # Calculate bearing between two consecutive points
                bearing = calculate_bearing((prev_lon, prev_lat), (lon, lat))

                # Add arrow marker at the end of the line using a regular polygon marker
                arrow = folium.RegularPolygonMarker(location=((lat + prev_lat) / 2, (lon + prev_lon) / 2), color=color, fill_color=color, weight=6, number_of_sides=3, radius=7, rotation=bearing - 90)
                map.add_child(arrow)
        prev_points[mmsi].append((lon, lat, time))

    map_html = map._repr_html_()
    return map_html

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/map', methods=['GET', 'POST'])
def map():
    if request.method == 'POST':

        return redirect(url_for('map'))
    sql_query = f"SELECT * FROM {DATA_STORE_TABLE}"
    query_result = execute_sql_query(sql_query)
    map_html = map_plot(query_result)
    return render_template('index.html', map_html=map_html)

@app.route('/filter', methods=['POST'])
def filter_data():
    # shipname, mmsi, start_datetime, end_datetime = None
    mmsi = ['']
    shipname = [name.strip() for name in request.form['shipNames'].split(",")]
    if request.form['mmsi']:
        mmsi = [int(name.strip()) for name in request.form['mmsi'].split(",")]
    start_datetime = request.form['timeRange1']
    start_datetime = start_datetime.replace('T', ' ')
    end_datetime = request.form['timeRange2']
    end_datetime = end_datetime.replace('T', ' ')
    sql_query = query(shipname, mmsi, start_datetime, end_datetime)
    print(sql_query)
    query_result = execute_sql_query(sql_query)
    map_html = map_plot(query_result)
    return render_template('index.html', map_html=map_html)


if __name__ == '__main__':
    app.run(debug=True)