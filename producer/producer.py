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

AIS_STREAM_URL = os.getenv("AIS_STREAM_URL", "wss://stream.aisstream.io/v0/stream")
AIS_SOURCE_NAME = os.getenv("AIS_SOURCE_NAME", "aisstream.io")
TOPIC_POSITION = os.getenv("TOPIC_NAME_1", "aisstream1")
TOPIC_STATIC = os.getenv("TOPIC_NAME_2", "aisstream2")
FLUSH_EVERY = 50

# Sentinels defined by the AIS standard for "not available"; the website
# renders them as N/A.
SOG_NOT_AVAILABLE = 102.3
COG_NOT_AVAILABLE = 360.0
HEADING_NOT_AVAILABLE = 511
NAV_STATUS_NOT_AVAILABLE = 15

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
        {"name": "time", "type": "string"},
        {"name": "sog", "type": "float"},
        {"name": "cog", "type": "float"},
        {"name": "heading", "type": "int"},
        {"name": "nav_status", "type": "int"},
        {"name": "source", "type": "string"}
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


def delivery_report(err, msg):
    """
    Logs failed deliveries; successful ones stay quiet to keep logs usable.
    """
    if err is not None:
        print(f"Message delivery failed: {err}", flush=True)


def extract_position(message):
    """
    Turns an aisstream.io PositionReport message into the two records we
    publish to Kafka (position/motion data and static name data).
    """
    ais_message = message['Message']['PositionReport']
    meta_message = message['MetaData']
    utc_plus_8_time = datetime.now(timezone.utc) + timedelta(hours=8)
    time_str = utc_plus_8_time.strftime("%Y-%m-%d %H:%M:%S")

    def field(container, key, default):
        value = container.get(key)
        return default if value is None else value

    position = {
        "MMSI": meta_message['MMSI'],
        "lat": ais_message['Latitude'],
        "lng": ais_message['Longitude'],
        "time": time_str,
        "sog": float(field(ais_message, 'Sog', SOG_NOT_AVAILABLE)),
        "cog": float(field(ais_message, 'Cog', COG_NOT_AVAILABLE)),
        "heading": int(field(ais_message, 'TrueHeading', HEADING_NOT_AVAILABLE)),
        "nav_status": int(field(ais_message, 'NavigationalStatus', NAV_STATUS_NOT_AVAILABLE)),
        "source": AIS_SOURCE_NAME,
    }
    static = {
        "MMSI": meta_message['MMSI'],
        "ship_name": meta_message['ShipName'],
    }
    return position, static


def produce_records(position, static):
    producer.produce(
        topic=TOPIC_POSITION,
        value=avro_serializer1(position, SerializationContext(TOPIC_POSITION, MessageField.VALUE)),
        callback=delivery_report,
    )
    producer.produce(
        topic=TOPIC_STATIC,
        value=avro_serializer2(static, SerializationContext(TOPIC_STATIC, MessageField.VALUE)),
        callback=delivery_report,
    )
    producer.poll(0)


async def ais_producer():
    """
    Keeps one persistent websocket connection to aisstream.io and streams
    every PositionReport into Kafka, reconnecting with backoff on failure.
    (Previously a new connection was opened per message, which throttled
    throughput to a crawl.)
    """
    subscribe_message = os.getenv("SUBSCRIPTION_JSON")
    if subscribe_message is None:
        raise ValueError("Subscription JSON not found in environment variables.")

    backoff = 1
    while True:
        try:
            async with websockets.connect(AIS_STREAM_URL) as websocket:
                await websocket.send(subscribe_message)
                print(f"Connected to {AIS_STREAM_URL}, streaming...", flush=True)
                backoff = 1
                produced = 0
                async for message_json in websocket:
                    try:
                        message = json.loads(message_json)
                        if message.get("MessageType") != "PositionReport":
                            continue
                        position, static = extract_position(message)
                        produce_records(position, static)
                    except (KeyError, TypeError, ValueError, BufferError) as e:
                        # A single malformed message must not tear down the
                        # websocket connection.
                        print(f"Skipping bad message: {e}", flush=True)
                        continue
                    produced += 1
                    if produced % FLUSH_EVERY == 0:
                        producer.flush()
        except Exception as e:
            print(f"Stream error: {e}. Reconnecting in {backoff}s...", flush=True)
            producer.flush()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(ais_producer())
