import asyncio
import json
from datetime import datetime, timedelta, timezone
import websockets
from producer import *
from confluent_kafka.avro import AvroProducer
import avro.schema

avro_schema_str1 = """
{
    "type": "record",
    "name": "AISData1",
    "fields": [
        {"name": "MMSI", "type": "int"},
        {"name": "lat", "type": "float"},
        {"name": "lng", "type": "float"},
        {"name": "time", "type": "string"}
    ]
}
"""

avro_schema_str2 = """
{
    "type": "record",
    "name": "AISData2",
    "fields": [
        {"name": "MMSI", "type": "int"},
        {"name": "ship_name", "type": "string"}
    ]
}
"""

avro_schema1 = avro.schema.parse(avro_schema_str1)
avro_schema2 = avro.schema.parse(avro_schema_str2)

async def ais_stream():
    try:
        async with websockets.connect("wss://stream.aisstream.io/v0/stream") as websocket:
            with open("subscription.json", "r") as f:
                subscribe_message = json.load(f)

            subscribe_message_json = json.dumps(subscribe_message)
            await websocket.send(subscribe_message_json)

            async for message_json in websocket:
                message = json.loads(message_json)
                message_type = message["MessageType"]
                if message_type == "PositionReport":
                    ais_message = message['Message']['PositionReport']
                    meta_message = message['MetaData']

                    utc_plus_8_time = datetime.now(timezone.utc) + timedelta(hours=8)
                    utc_plus_8_time_str = utc_plus_8_time.strftime("%Y-%m-%d %H:%M:%S")

                    return {"MMSI": meta_message['MMSI'], "ship_name": meta_message['ShipName'], "lat": ais_message['Latitude'], "lng": ais_message['Longitude'], "time": utc_plus_8_time_str}
                
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

async def ais_producer():
    bootstrap_servers = 'broker:29092'
    conf = {
        'bootstrap.servers': bootstrap_servers,
        'schema.registry.url': 'http://schema-registry:8081'
    }
    
    while True:
        data = await ais_stream()
        if data is not None:
            data1 = {"MMSI": data['MMSI'], "ship_name": data['ship_name']}
            data2 = {"MMSI": data['MMSI'], "lat": data['lat'], "lng": data['lng'], "time": data['time']}
            TOPIC1 = 'aisstream1'
            producer1 = AvroProducer(conf, default_value_schema=avro_schema2)
            data_stream(data1, TOPIC1, producer1)
            TOPIC2 = 'aisstream2'
            producer2 = AvroProducer(conf, default_value_schema=avro_schema1)
            data_stream(data2, TOPIC2, producer2)
        else:
            print("Failed to retrieve data from AIS stream.")

if __name__ == "__main__":
    asyncio.run(ais_producer())
