from confluent_kafka.avro import AvroConsumer

conf = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'my_consumer_group',  
    'auto.offset.reset': 'earliest',  
    'schema.registry.url': 'http://localhost:8081'  
}

consumer = AvroConsumer(conf)
topic = "aisstream"
consumer.subscribe([topic])

try:
    while True:
        msg = consumer.poll(timeout=1.0)  
        if msg is None:
            continue
        if msg.error():
            print(f"Error: {msg.error()}")
            continue
        print(f"Received message: {msg.value()}")  
except KeyboardInterrupt:
    pass
finally:
    consumer.close()
