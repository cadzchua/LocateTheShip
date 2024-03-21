# Aisstream

## Description

Streaming aisstream.io data to kafka.

### Files/Folders

"producer" folder: main code for streaming data to kafka.

"consumer" folder: main code for consuming data from kafka.

"application": main code for running Flask and querying database to plot ship's coordinates.

"docker-compose.yaml": code for configuring Docker Compose.

## Requirements

- Python 3
- Pip
- Docker Desktop

## Usage
### Start the containers
```linux
# run the containers
# use Docker Desktop to see if containers are running
docker compose up [-d]
```
---
Head over to `localhost:8978` to configure the GUI for the postgresDB.
![Picture1!](<README/photos/Screenshot 2024-03-21 183936.png>)

Make sure to press the **Create** button after configuring.

---
Next, head over to `localhost:9021` to set up the JDBC Sink Connector for streaming data from Kafka to the PostgreSQL database.

![Picture2!](<README/photos/Screenshot 2024-03-21 184438.png>)

Make sure **aisstream1** and **aisstream2** are present in topics.

---
![Picture3!](<README/photos/Screenshot 2024-03-21 184453.png>)
```sql
CREATE STREAM aisstream1 WITH (
    KAFKA_TOPIC='aisstream1',  
    VALUE_FORMAT='AVRO'  
);

CREATE STREAM aisstream2 WITH (
    KAFKA_TOPIC='aisstream2',  
    VALUE_FORMAT='AVRO'  
);

CREATE STREAM aisstream_combined WITH (
    KAFKA_TOPIC='aisstream_combined',
    VALUE_FORMAT='AVRO'
) AS
    SELECT
        AISSTREAM2.SHIP_NAME AS SHIP_NAME,
        AISSTREAM2.MMSI AS MMSI1,
        AISSTREAM1.MMSI AS MMSI,
        AISSTREAM1.lat AS LATITUDE,
        AISSTREAM1.lng AS LONGITUDE,
        AISSTREAM1.time AS TIME
    FROM aisstream2 
    JOIN aisstream1
    WITHIN 5 SECONDS  
    ON aisstream1.MMSI = aisstream2.MMSI;
```
Type in the above code and **run query**.

---
![Picture4!](<README/photos/Screenshot 2024-03-21 185127.png>)
Go to connect and setup a JDBCSinkConnector with the following configurations.
**Ensure that auto.create is True!** Check if the connector is running after launching it.

You can check cloudbeaver (`localhost:8978`), if data are streaming into the PostgresDB.

---
### Stop the containers
```linux
# stop running the containers and remove the network for shopping list
docker compose down 
```

## Contributing

Contributions to the Aisstream project are welcomed. If you plan to make significant changes, please open an issue first to discuss the proposed modifications. 
Additionally, ensure that you update the relevant tests to maintain code integrity.

## Authors

The Aisstream application is maintained by cadzchua.

## License

This project is licensed under the [MIT](https://choosealicense.com/licenses/mit/). You are free to use, modify, and distribute the software as per the terms of the license agreement.
