import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("influxdb.writer")

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "factory/machine1/sensors")
INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "meu-token-influx")
INFLUX_ORG = os.getenv("INFLUX_ORG", "minha-org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_dados")
MACHINE_TAG = os.getenv("MACHINE_TAG", "machine1")

influx_client: InfluxDBClient | None = None
write_api = None


def init_influx() -> None:
    global influx_client, write_api
    for attempt in range(1, 16):
        try:
            influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            log.info("InfluxDB ligado em %s", INFLUX_URL)
            return
        except Exception as exc:
            log.warning("InfluxDB indisponivel (%s/15): %s", attempt, exc)
            time.sleep(5)
    raise RuntimeError("Nao foi possivel ligar ao InfluxDB")


def write_to_influx(data: dict) -> None:
    if write_api is None:
        raise RuntimeError("write_api ainda nao foi inicializado")

    point = build_point(data)
    write_api.write(bucket=INFLUX_BUCKET, record=point)
    log.info(
        "Persistido no InfluxDB: T=%s P=%s Estado=%s Alarm=%s",
        data.get("temperature"),
        data.get("pressure"),
        data.get("machine_state_name"),
        data.get("alarm_name"),
    )


def build_point(data: dict) -> Point:
    return (
        Point("machine_metrics")
        .tag("machine", MACHINE_TAG)
        .tag("machine_state", str(data.get("machine_state_name", "UNKNOWN")))
        .tag("alarm", str(data.get("alarm_name", "OK")))
        .field("temperature", float(data.get("temperature", 0)))
        .field("pressure", float(data.get("pressure", 0)))
        .field("humidity", float(data.get("humidity", 0)))
        .field("vibration", float(data.get("vibration", 0)))
        .field("power_kw", float(data.get("power_kw", 0)))
        .field("cycle_count", int(data.get("cycle_count", 0)))
        .field("uptime_s", int(data.get("uptime_s", 0)))
        .field("alarm_code", int(data.get("alarm_code", 0)))
        .field("valid", bool(data.get("valid", True)))
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )


def is_success(reason_code) -> bool:
    return getattr(reason_code, "value", reason_code) == 0


def on_connect(client, _userdata, _flags, reason_code, _properties) -> None:
    if is_success(reason_code):
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info("MQTT ligado e subscrito em %s", MQTT_TOPIC)
    else:
        log.error("Falha na ligacao MQTT: %s", reason_code)


def on_message(_client, _userdata, msg) -> None:
    try:
        data = json.loads(msg.payload.decode())
        write_to_influx(data)
    except json.JSONDecodeError as exc:
        log.error("Payload MQTT invalido: %s", exc)
    except Exception as exc:
        log.error("Erro ao processar mensagem MQTT: %s", exc)


def on_disconnect(_client, _userdata, _flags, reason_code, _properties) -> None:
    log.warning("MQTT desligado com codigo %s", reason_code)


def main() -> None:
    time.sleep(int(os.getenv("STARTUP_DELAY", "10")))
    init_influx()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="influxdb_writer")
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    for attempt in range(1, 11):
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            break
        except Exception as exc:
            log.warning("MQTT indisponivel (%s/10): %s", attempt, exc)
            time.sleep(5)
    else:
        raise RuntimeError("Nao foi possivel ligar ao broker MQTT")

    def shutdown(_sig, _frame) -> None:
        log.info("A encerrar writer InfluxDB...")
        client.disconnect()
        if influx_client is not None:
            influx_client.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("Writer em execucao a aguardar mensagens MQTT...")
    client.loop_forever()


if __name__ == "__main__":
    main()
