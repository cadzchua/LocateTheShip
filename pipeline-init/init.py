"""One-shot bootstrap for the AIS pipeline.

Replaces the manual setup that used to be done in Confluent Control Center:
it creates the ksqlDB streams (including the joined aisstream_combined
stream) and registers the JDBC sink connector that writes the joined
stream into PostgreSQL. Every step is idempotent and retried, so the
service can start before the broker, schema registry, ksqlDB, Connect or
the producer are ready.
"""

import json
import os
import time
import urllib.error
import urllib.request

KSQLDB_URL = os.getenv("KSQLDB_URL", "http://ksqldb-server:8088").rstrip("/")
CONNECT_URL = os.getenv("CONNECT_URL", "http://connect:8083").rstrip("/")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081").rstrip("/")

DB_HOST = os.getenv("DATA_STORE_HOST", "postgres")
DB_PORT = os.getenv("DATA_STORE_PORT", "5432")
DB_NAME = os.getenv("DATA_STORE_DATABASE", "postgres")
DB_USER = os.getenv("DATA_STORE_USER", "sa")
DB_PASSWORD = os.getenv("DATA_STORE_PASSWORD", "YourStrongPassword123")

CONNECTOR_NAME = os.getenv("CONNECTOR_NAME", "ais-postgres-sink")
TOPIC_POSITION = os.getenv("TOPIC_NAME_1", "aisstream1")
TOPIC_STATIC = os.getenv("TOPIC_NAME_2", "aisstream2")
TOPIC_COMBINED = os.getenv("TOPIC_COMBINED", "aisstream_combined")

RETRY_SECONDS = 5

# The source streams have no explicit columns: ksqlDB pulls the value
# schema from the schema registry, so these statements only succeed once
# the producer has published at least one message per topic. The retry
# loop below waits for that.
KSQL_STATEMENTS = [
    f"""
    CREATE STREAM IF NOT EXISTS {TOPIC_POSITION} WITH (
        KAFKA_TOPIC='{TOPIC_POSITION}',
        VALUE_FORMAT='AVRO'
    );
    """,
    f"""
    CREATE STREAM IF NOT EXISTS {TOPIC_STATIC} WITH (
        KAFKA_TOPIC='{TOPIC_STATIC}',
        VALUE_FORMAT='AVRO'
    );
    """,
    f"""
    CREATE STREAM IF NOT EXISTS {TOPIC_COMBINED} WITH (
        KAFKA_TOPIC='{TOPIC_COMBINED}',
        VALUE_FORMAT='AVRO'
    ) AS
    SELECT
        {TOPIC_STATIC}.MMSI AS AIS_MMSI1,
        {TOPIC_STATIC}.SHIP_NAME AS AIS_SHIP_NAME,
        {TOPIC_POSITION}.MMSI AS AIS_MMSI,
        {TOPIC_POSITION}.lat AS AIS_LATITUDE,
        {TOPIC_POSITION}.lng AS AIS_LONGITUDE,
        {TOPIC_POSITION}.time AS AIS_TIME,
        {TOPIC_POSITION}.sog AS AIS_SOG,
        {TOPIC_POSITION}.cog AS AIS_COG,
        {TOPIC_POSITION}.heading AS AIS_HEADING,
        {TOPIC_POSITION}.nav_status AS AIS_NAV_STATUS,
        {TOPIC_POSITION}.source AS AIS_SOURCE
    FROM {TOPIC_STATIC}
    JOIN {TOPIC_POSITION}
    WITHIN 5 SECONDS
    ON {TOPIC_POSITION}.MMSI = {TOPIC_STATIC}.MMSI;
    """,
]

CONNECTOR_CONFIG = {
    "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
    "tasks.max": "1",
    "topics": TOPIC_COMBINED,
    "connection.url": f"jdbc:postgresql://{DB_HOST}:{DB_PORT}/{DB_NAME}",
    "connection.user": DB_USER,
    "connection.password": DB_PASSWORD,
    "insert.mode": "insert",
    "pk.mode": "none",
    "auto.create": "true",
    "auto.evolve": "true",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": SCHEMA_REGISTRY_URL,
}


def request(method, url, body=None, content_type="application/json"):
    """Perform an HTTP request and return (status, response text)."""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8")


def wait_for(url, name):
    while True:
        try:
            request("GET", url)
            print(f"[init] {name} is reachable", flush=True)
            return
        except Exception as exc:
            print(f"[init] waiting for {name} ({exc})", flush=True)
            time.sleep(RETRY_SECONDS)


def run_ksql(statement):
    body = {
        "ksql": statement,
        "streamsProperties": {"ksql.streams.auto.offset.reset": "earliest"},
    }
    try:
        status, text = request(
            "POST",
            f"{KSQLDB_URL}/ksql",
            body,
            content_type="application/vnd.ksql.v1+json; charset=utf-8",
        )
        return True, text
    except urllib.error.HTTPError as err:
        return False, err.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return False, str(exc)


def create_streams():
    for statement in KSQL_STATEMENTS:
        summary = statement.strip().splitlines()[0]
        while True:
            ok, detail = run_ksql(statement)
            if ok:
                print(f"[init] ok: {summary}", flush=True)
                break
            if "already exists" in detail.lower():
                print(f"[init] already exists, skipping: {summary}", flush=True)
                break
            print(
                f"[init] not ready yet ({summary}). ksqlDB said: {detail[:300]}",
                flush=True,
            )
            time.sleep(RETRY_SECONDS)


def create_connector():
    url = f"{CONNECT_URL}/connectors/{CONNECTOR_NAME}/config"
    while True:
        try:
            status, _ = request("PUT", url, CONNECTOR_CONFIG)
            print(f"[init] connector '{CONNECTOR_NAME}' configured (HTTP {status})", flush=True)
            return
        except Exception as exc:
            print(f"[init] connector setup failed, retrying ({exc})", flush=True)
            time.sleep(RETRY_SECONDS)


def main():
    print("[init] bootstrapping AIS pipeline", flush=True)
    wait_for(f"{KSQLDB_URL}/info", "ksqlDB")
    wait_for(f"{CONNECT_URL}/connectors", "Kafka Connect")
    create_streams()
    create_connector()
    print("[init] pipeline ready: data now flows aisstream.io -> Kafka -> ksqlDB -> PostgreSQL", flush=True)


if __name__ == "__main__":
    main()
