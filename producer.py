from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import random
from confluent_kafka.serialization import (
    SerializationContext,
    MessageField,
)

schema_registry_conf = {'url': 'http://localhost:8081'}
schema_registry_client = SchemaRegistryClient(schema_registry_conf)

with open("telemetry.avsc") as f:
    value_schema = f.read()

avro_serializer = AvroSerializer(schema_registry_client, value_schema)

producer_conf = {'bootstrap.servers': 'localhost:9092'}


producer = Producer(producer_conf)

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")

for i in range(20):
    temperature = round(random.uniform(0, 100), 2)

    event = {
        "index": i,
        "temp": temperature
    }

    producer.produce(
    topic="telemetry",
    value=avro_serializer(event, SerializationContext("telemetry", MessageField.VALUE)),
)
    print(i)
producer.flush()