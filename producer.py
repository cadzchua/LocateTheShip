import json
import random
import time
import schedule
from confluent_kafka import avro
from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro.serializer import SerializerError

avro_schema_str = """
{
    "type": "record",
    "name": "TemperatureData",
    "fields": [
        {"name": "temperature", "type": "float"}
    ]
}
"""

avro_schema = avro.loads(avro_schema_str)

def data_stream(data, topic, producer):
    try:
        producer.produce(topic=topic, value=data, callback=delivery_report)
        producer.flush()
    except SerializerError as e:
        print(f"Failed to produce message: {e}")

def delivery_report(err, msg):
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')
        
if __name__ == '__main__':
    topic = "AISstream.io"
    bootstrap_servers = 'localhost:9092'
    conf = {
        'bootstrap.servers': bootstrap_servers,
        'schema.registry.url': 'http://localhost:8081'
    }
    producer = AvroProducer(conf, default_value_schema=avro_schema)
    while True:
        temperature_data = {'temperature': random.uniform(10.0, 110.0)}
        data_stream(temperature_data, topic, producer)
