import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Callable, Optional

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException


class Register(IntEnum):
    TEMPERATURE = 0
    PRESSURE = 1
    MACHINE_STATE = 2
    CYCLE_COUNT = 3
    ALARM_CODE = 4
    UPTIME_HI = 5
    UPTIME_LO = 6
    HUMIDITY = 7
    VIBRATION = 8
    POWER_KW = 9


STATE_NAMES = {
    0: "OFF",
    1: "IDLE",
    2: "WARMING",
    3: "RUNNING",
    4: "COOLING",
    5: "ERROR",
}

ALARM_NAMES = {
    0: "OK",
    1: "OVERHEAT",
    2: "OVERPRESSURE",
    3: "VIBRATION_HIGH",
}

SANITY_LIMITS = {
    "temperature": (0.0, 120.0),
    "pressure": (0.0, 20.0),
    "humidity": (0.0, 100.0),
    "vibration": (0.0, 50.0),
    "power_kw": (0.0, 100.0),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("modbus.client")


@dataclass
class SensorReading:
    timestamp: float = field(default_factory=time.time)
    temperature: float = 0.0
    pressure: float = 0.0
    machine_state: int = 0
    machine_state_name: str = "UNKNOWN"
    cycle_count: int = 0
    alarm_code: int = 0
    alarm_name: str = "OK"
    uptime_s: int = 0
    humidity: float = 0.0
    vibration: float = 0.0
    power_kw: float = 0.0
    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["timestamp_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp))
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class ResilientModbusClient:
    def __init__(
        self,
        host: str,
        port: int,
        poll_interval: float,
        slave_id: int = 1,
        max_retries: int = 5,
    ) -> None:
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self.slave_id = slave_id
        self.max_retries = max_retries
        self._client: Optional[ModbusTcpClient] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable[[SensorReading], None]] = []

    def on_reading(self, callback: Callable[[SensorReading], None]) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("Cliente Modbus ligado ao alvo %s:%s", self.host, self.port)

    def stop(self) -> None:
        self._running = False
        if self._client:
            self._client.close()

    def _connect(self) -> bool:
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            try:
                self._client = ModbusTcpClient(self.host, port=self.port, timeout=3)
                if self._client.connect():
                    log.info("Ligacao Modbus estabelecida na tentativa %s", attempt)
                    return True
            except Exception as exc:
                log.warning("Tentativa Modbus %s falhou: %s", attempt, exc)
            time.sleep(delay)
            delay = min(delay * 2, 30)
        return False

    def _do_read(self) -> Optional[SensorReading]:
        if not self._client or not self._client.is_socket_open():
            if not self._connect():
                return None

        try:
            result = self._client.read_holding_registers(0, count=10, slave=self.slave_id)
        except (ConnectionException, ModbusException) as exc:
            log.error("Erro Modbus: %s", exc)
            self._client = None
            return None

        if result.isError():
            log.error("Resposta Modbus com erro: %s", result)
            return None

        reading = parse_registers(result.registers)
        self._validate(reading)
        return reading

    def _validate(self, reading: SensorReading) -> None:
        values = {
            "temperature": reading.temperature,
            "pressure": reading.pressure,
            "humidity": reading.humidity,
            "vibration": reading.vibration,
            "power_kw": reading.power_kw,
        }
        for field_name, value in values.items():
            low, high = SANITY_LIMITS[field_name]
            if not low <= value <= high:
                reading.valid = False
                reading.errors.append(f"{field_name}={value} fora do intervalo [{low}, {high}]")

    def _poll_loop(self) -> None:
        while self._running:
            started = time.monotonic()
            with self._lock:
                reading = self._do_read()

            if reading:
                for callback in self._callbacks:
                    try:
                        callback(reading)
                    except Exception as exc:
                        log.error("Callback falhou: %s", exc)
                log.info(
                    "[%s] T=%.2fC P=%.2fbar Hum=%.2f%% Vib=%.2f Power=%.2fkW Alarm=%s",
                    reading.machine_state_name,
                    reading.temperature,
                    reading.pressure,
                    reading.humidity,
                    reading.vibration,
                    reading.power_kw,
                    reading.alarm_name,
                )
            else:
                log.warning("Leitura Modbus falhou")

            elapsed = time.monotonic() - started
            time.sleep(max(0.0, self.poll_interval - elapsed))


def build_mqtt_publisher(broker_host: str, broker_port: int, topic_prefix: str) -> Callable[[SensorReading], None]:
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="modbus_client")

    def is_success(reason_code) -> bool:
        return getattr(reason_code, "value", reason_code) == 0

    def on_connect(_client, _userdata, _flags, reason_code, _properties) -> None:
        if is_success(reason_code):
            log.info("MQTT ligado a %s:%s", broker_host, broker_port)
        else:
            log.error("Falha na ligacao MQTT: %s", reason_code)

    mqtt_client.on_connect = on_connect

    for attempt in range(1, 11):
        try:
            mqtt_client.connect(broker_host, broker_port, keepalive=60)
            mqtt_client.loop_start()
            break
        except Exception as exc:
            log.warning("MQTT indisponivel (%s/10): %s", attempt, exc)
            time.sleep(5)
    else:
        raise RuntimeError("Nao foi possivel ligar ao broker MQTT")

    def publish(reading: SensorReading) -> None:
        if not reading.valid:
            log.warning("Leitura invalida ignorada: %s", reading.errors)
            return

        mqtt_client.publish(f"{topic_prefix}/sensors", reading.to_json(), qos=1)
        mqtt_client.publish(f"{topic_prefix}/temperature", str(reading.temperature), qos=0)
        mqtt_client.publish(f"{topic_prefix}/pressure", str(reading.pressure), qos=0)
        mqtt_client.publish(f"{topic_prefix}/state", reading.machine_state_name, qos=0)

    return publish


def parse_registers(registers: list[int]) -> SensorReading:
    return SensorReading(
        temperature=registers[Register.TEMPERATURE] / 100.0,
        pressure=registers[Register.PRESSURE] / 100.0,
        machine_state=registers[Register.MACHINE_STATE],
        machine_state_name=STATE_NAMES.get(registers[Register.MACHINE_STATE], "UNKNOWN"),
        cycle_count=registers[Register.CYCLE_COUNT],
        alarm_code=registers[Register.ALARM_CODE],
        alarm_name=ALARM_NAMES.get(registers[Register.ALARM_CODE], "UNKNOWN"),
        uptime_s=(registers[Register.UPTIME_HI] << 16) | registers[Register.UPTIME_LO],
        humidity=registers[Register.HUMIDITY] / 100.0,
        vibration=registers[Register.VIBRATION] / 100.0,
        power_kw=registers[Register.POWER_KW] / 10.0,
    )


def main() -> None:
    modbus_host = os.getenv("MODBUS_HOST", "modbus_server")
    modbus_port = int(os.getenv("MODBUS_PORT", "5020"))
    poll_interval = float(os.getenv("POLL_INTERVAL", "5"))
    mqtt_host = os.getenv("MQTT_HOST", "mosquitto")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    topic_prefix = os.getenv("MQTT_TOPIC_PREFIX", "factory/machine1")

    time.sleep(int(os.getenv("STARTUP_DELAY", "5")))

    client = ResilientModbusClient(modbus_host, modbus_port, poll_interval)

    def alarm_watcher(reading: SensorReading) -> None:
        if reading.alarm_code:
            log.warning("ALARME ATIVO: %s (%s)", reading.alarm_name, reading.alarm_code)

    client.on_reading(alarm_watcher)
    client.on_reading(build_mqtt_publisher(mqtt_host, mqtt_port, topic_prefix))
    client.start()

    def shutdown(_sig, _frame) -> None:
        log.info("A encerrar cliente Modbus...")
        client.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
