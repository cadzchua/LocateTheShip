from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import asyncio, websockets, json
from datetime import datetime, timedelta, timezone
from confluent_kafka.serialization import (
    SerializationContext,
    MessageField,
)
import os

schema_registry_conf = {'url': f'{os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")}'}
schema_registry_client = SchemaRegistryClient(schema_registry_conf)

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

avro_serializer1 = AvroSerializer(schema_registry_client, avro_schema_str1)
avro_serializer2 = AvroSerializer(schema_registry_client, avro_schema_str2)
producer_conf = {'bootstrap.servers': os.getenv("KAFKA_BOOTSTRAP_SERVER", default="localhost:9092")}
producer = Producer(producer_conf)

async def ais_stream():
    """ 
    Retrives the information from the aisstream API and returns it.
    """
    try:
        async with websockets.connect("wss://stream.aisstream.io/v0/stream") as websocket:
            subscribe_message = os.getenv("SUBSCRIPTION_JSON")
            if subscribe_message is None:
                raise ValueError("Subscription JSON not found in environment variables.")
            
            await websocket.send(subscribe_message)
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
    
def delivery_report(err, msg):
    """ 
    Gives a report whether the message is successfully streaming.
    """
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")

async def ais_producer():
    """
    Streaming the data to kafka
    note: currently 2 separate streams to be combined later using sql (for learning purposes)
    """
    while True:
        data = await ais_stream()
        if data is not None:
            data1 = {"MMSI": data['MMSI'], "lat": data['lat'], "lng": data['lng'], "time": data['time']}
            data2 = {"MMSI": data['MMSI'], "ship_name": data['ship_name']}
            producer.produce(topic="aisstream1", value=avro_serializer1(data1, SerializationContext("aisstream1", MessageField.VALUE)), callback=delivery_report)
            producer.produce(topic="aisstream2", value=avro_serializer2(data2, SerializationContext("aisstream2", MessageField.VALUE)), callback=delivery_report)
            producer.flush()
        else:
            print("Failed to retrieve data from AIS stream.")

if __name__ == "__main__":
    asyncio.run(ais_producer())