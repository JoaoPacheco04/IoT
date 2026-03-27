from tests.conftest import load_module


writer = load_module("influxdb_writer_module", "influxdb_writer/influxdb.py")


def test_build_point_contains_expected_tags_and_fields():
    payload = {
        "timestamp": 1711576800.0,
        "temperature": 25.34,
        "pressure": 8.76,
        "humidity": 54.32,
        "vibration": 1.23,
        "power_kw": 4.5,
        "cycle_count": 12,
        "uptime_s": 123,
        "alarm_code": 2,
        "valid": True,
        "machine_state_name": "RUNNING",
        "alarm_name": "OVERPRESSURE",
    }

    point = writer.build_point(payload)
    line = point.to_line_protocol()

    assert "machine_metrics" in line
    assert "machine_state=RUNNING" in line
    assert "alarm=OVERPRESSURE" in line
    assert "temperature=25.34" in line
    assert "pressure=8.76" in line
    assert "cycle_count=12i" in line
    assert line.endswith("1711576800000000000")


def test_write_to_influx_uses_configured_bucket():
    captured = {}

    class FakeWriteApi:
        def write(self, bucket, record):
            captured["bucket"] = bucket
            captured["record"] = record

    writer.write_api = FakeWriteApi()
    writer.write_to_influx({"temperature": 22.5, "pressure": 5.1})

    assert captured["bucket"] == writer.INFLUX_BUCKET
    assert "machine_metrics" in captured["record"].to_line_protocol()
