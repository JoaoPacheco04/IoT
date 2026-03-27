from tests.conftest import load_module


client_module = load_module("modbus_client_module", "modbus_client/client.py")


def test_parse_registers_builds_sensor_reading():
    registers = [2534, 876, 3, 12, 2, 0, 123, 5432, 123, 45]

    reading = client_module.parse_registers(registers)

    assert reading.temperature == 25.34
    assert reading.pressure == 8.76
    assert reading.machine_state == 3
    assert reading.machine_state_name == "RUNNING"
    assert reading.cycle_count == 12
    assert reading.alarm_code == 2
    assert reading.alarm_name == "OVERPRESSURE"
    assert reading.uptime_s == 123
    assert reading.humidity == 54.32
    assert reading.vibration == 1.23
    assert reading.power_kw == 4.5


def test_validate_marks_invalid_values():
    client = client_module.ResilientModbusClient("localhost", 5020, 5)
    reading = client_module.SensorReading(temperature=999.0, pressure=8.0, humidity=50.0, vibration=1.0, power_kw=2.0)

    client._validate(reading)

    assert reading.valid is False
    assert any("temperature" in error for error in reading.errors)
