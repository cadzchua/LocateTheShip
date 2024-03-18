from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka import Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient

class BasicContext:
    def __init__(self, schema_registry_url):
        self.schema_registry = SchemaRegistryClient({'url': schema_registry_url})

    def get_schema(self, subject, version=None):
        return self.schema_registry.get_latest_schema(subject)
    
conf = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'my_consumer_group',  
    'auto.offset.reset': 'earliest',  
    'schema.registry.url': 'http://localhost:8081'  
}
ctx = BasicContext(conf['schema.registry.url'])
avro_deserializer = AvroDeserializer(ctx.schema_registry)

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")

consumer_conf = {
    'bootstrap.servers': conf['bootstrap.servers'],
    'group.id': conf['group.id'],
    'auto.offset.reset': conf['auto.offset.reset']
}

consumer = Consumer(consumer_conf)

topic = "telemetry"
consumer.subscribe([topic])

try:
    while True:
        msg = consumer.poll(timeout=1.0)  
        if msg is None:
            continue
        if msg.error():
            print(f"Error: {msg.error()}")
            continue
        decoded_msg = avro_deserializer(msg.value(), ctx=ctx)
        print(f"Received message: {decoded_msg}")
except KeyboardInterrupt:
    pass
finally:
    consumer.close()
