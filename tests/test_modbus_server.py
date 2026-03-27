from tests.conftest import load_module


server = load_module("modbus_server_module", "modbus_server/server.py")


def test_machine_simulator_to_registers_scales_values():
    machine = server.MachineSimulator()
    machine.temperature = 25.34
    machine.pressure = 8.76
    machine.humidity = 54.32
    machine.vibration = 1.23
    machine.power_kw = 4.5
    machine.cycle_count = 7
    machine.alarm_code = 2

    registers = machine.to_registers()

    assert len(registers) == 10
    assert registers[server.Register.TEMPERATURE] == 2534
    assert registers[server.Register.PRESSURE] == 876
    assert registers[server.Register.CYCLE_COUNT] == 7
    assert registers[server.Register.ALARM_CODE] == 2
    assert registers[server.Register.HUMIDITY] == 5432
    assert registers[server.Register.VIBRATION] == 123
    assert registers[server.Register.POWER_KW] == 45


def test_machine_simulator_uptime_registers_are_non_negative():
    machine = server.MachineSimulator()

    registers = machine.to_registers()
    uptime = (registers[server.Register.UPTIME_HI] << 16) | registers[server.Register.UPTIME_LO]

    assert uptime >= 0
