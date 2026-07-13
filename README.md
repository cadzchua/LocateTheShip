# Aisstream

## Description

A self contained AIS vessel tracking stack. A producer streams live ship position reports from aisstream.io into Kafka, ksqlDB joins the position and ship name streams, a JDBC sink connector writes the joined stream into PostgreSQL, and a Flask website plots the ships on an interactive map with per ship tracks, speed, course, heading and navigational status.

The entire pipeline configures itself. A one shot `pipeline-init` container creates the ksqlDB streams and the sink connector automatically, so there is no manual Control Center or CloudBeaver setup anymore.

### Architecture

aisstream.io websocket feeds the `ais-producer` service, which publishes Avro records to the Kafka topics `aisstream1` (position and motion data) and `aisstream2` (ship names). The `pipeline-init` service creates ksqlDB streams over both topics plus a joined `aisstream_combined` stream, then registers a JDBC sink connector that writes the joined stream into the `aisstream_combined` table in PostgreSQL. The `ais-website` service reads that table and renders the map at port 5000.

### Files and folders

The `producer` folder holds the code that streams aisstream.io data into Kafka. The `pipeline-init` folder holds the bootstrap script that creates the ksqlDB streams and the sink connector. The `application` folder holds the Flask website that queries the database and plots ship positions. The `consumer` folder holds a small standalone script for debugging Kafka topics from the command line. `docker-compose.yml` wires everything together.

## Requirements

Docker Desktop is the only requirement. Python is only needed if you want to run the scripts outside of Docker.

## Usage

```
docker compose up -d --build
```

Then open http://localhost:5000 and click through to the map. On a cold start the pipeline needs a minute or two before the first ships appear because Kafka, ksqlDB and Connect have to come up and the bootstrap has to run. The website shows a warming up page and retries automatically until data arrives.

To use your own aisstream.io API key, copy `.env.example` to `.env` and set `AISSTREAM_API_KEY`. Without it a built in demo key is used. The tracked area is defined by the bounding box in the `SUBSCRIPTION_JSON` block of `docker-compose.yml` and currently covers the waters around Singapore and the Malacca Strait.

### Map features

The map shows each ship's latest position as a small directional arrow rotated to its true heading (or course over ground when no heading is reported), colored consistently per ship across refreshes. Older reports appear as small dots connected by a track line. Hovering a marker shows the ship name, speed and report time. Clicking a marker opens the full details including MMSI, position, speed over ground, course over ground, heading, navigational status and the data source.

The filter panel supports comma separated ship names and MMSIs, a data source selector, a start and end time, and quick range buttons for the last 15 minutes, hour, 6 hours or 24 hours. An auto refresh toggle reloads the current view at a chosen interval, which keeps the picture live for monitoring. A stats bar shows how many ships and reports match the current query and the covered time window.

### Optional tooling

Confluent Control Center, CloudBeaver and the ksqlDB CLI are no longer needed for setup, so they are behind a compose profile to keep the default stack light. Start them when you want them with

```
docker compose --profile tools up -d
```

Control Center is then at http://localhost:9021 and CloudBeaver at http://localhost:8978.

### Upgrading from an older version

The pipeline now carries additional fields (speed, course, heading, navigational status and source), which changes the Kafka schemas and the database table. When upgrading an existing deployment, reset the stored state once with

```
docker compose down -v
docker compose up -d --build
```

### Stop the containers

```
docker compose down
```

## Contributing

Contributions to the Aisstream project are welcomed. If you plan to make significant changes, please open an issue first to discuss the proposed modifications. Additionally, ensure that you update the relevant tests to maintain code integrity.

## Authors

The Aisstream application is maintained by cadzchua.

## License

This project is licensed under the [MIT](LICENSE). You are free to use, modify, and distribute the software as per the terms of the license agreement.
