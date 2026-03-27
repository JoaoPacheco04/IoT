# Projeto IoT Industrial

Projeto prático de IoT industrial com integração entre Modbus TCP, MQTT, InfluxDB e Grafana.

Arquitetura da solução:

```text
Modbus TCP Server -> Modbus Client -> MQTT Broker -> InfluxDB Writer -> InfluxDB -> Grafana
```

O sistema simula uma máquina industrial, lê os registos periodicamente, publica os dados num broker MQTT, persiste-os numa base temporal e mostra-os num dashboard.

## Objetivos

- simular variáveis industriais num servidor Modbus TCP
- implementar um cliente Modbus para leitura periódica
- publicar os dados em MQTT
- persistir as leituras no InfluxDB
- visualizar os dados em Grafana

## Estrutura do projeto

```text
IoT_Projeto/
|-- docker-compose.yml
|-- .env
|-- README.md
|-- requirements-dev.txt
|-- config/
|   |-- mosquitto.conf
|   `-- grafana/
|       |-- dashboards/
|       `-- provisioning/
|-- modbus_server/
|   |-- server.py
|   |-- Dockerfile
|   `-- requirements.txt
|-- modbus_client/
|   |-- client.py
|   |-- Dockerfile
|   `-- requirements.txt
|-- influxdb_writer/
|   |-- influxdb.py
|   |-- Dockerfile
|   `-- requirements.txt
`-- tests/
    |-- test_modbus_server.py
    |-- test_modbus_client.py
    `-- test_influxdb_writer.py
```

## Componentes

### `modbus_server`

Servidor Modbus TCP que simula uma máquina industrial com:
- temperatura
- pressão
- estado da máquina
- contador de ciclos
- código de alarme
- uptime
- humidade
- vibração
- potência

Estados simulados:
- `OFF`
- `IDLE`
- `WARMING`
- `RUNNING`
- `COOLING`
- `ERROR`

Alarmes simulados:
- `OK`
- `OVERHEAT`
- `OVERPRESSURE`
- `VIBRATION_HIGH`

### `modbus_client`

Cliente Modbus que:
- lê os registos periodicamente
- converte os registos em leituras legíveis
- valida limites básicos
- publica os dados via MQTT

Tópico principal:

```text
factory/machine1/sensors
```

### `influxdb_writer`

Subscritor MQTT que recebe as leituras e grava no InfluxDB.

Measurement:

```text
machine_metrics
```

Bucket:

```text
iot_dados
```

### `mosquitto`

Broker MQTT usado entre o cliente Modbus e o writer.

Na rede Docker:
- host: `mosquitto`
- porta: `1883`

No host:
- MQTT: `1885`
- WebSocket: `9001`

### `influxdb`

Base de dados temporal para persistência das leituras.

No host:
- `http://localhost:8086`

### `grafana`

Dashboard para visualização dos dados persistidos no InfluxDB.

No host:
- `http://localhost:3001`

Inclui provisioning automático de:
- datasource InfluxDB
- dashboard inicial

## Decisões e ajustes feitos

Durante a implementação foram feitos alguns ajustes práticos:

- o MQTT no host foi exposto em `1885` para evitar conflito com outro broker local
- o Grafana ficou em `3001` para evitar conflito com outra instalação existente
- o servidor Modbus não foi exposto no host porque a porta `5020` já estava ocupada noutra stack
- a comunicação interna entre containers continua normal através da rede Docker

## Configuração

As variáveis principais estão em [.env](/c:/Users/joaop/Desktop/IoT_Projeto/.env).

Exemplos:
- `MODBUS_HOST=modbus_server`
- `MQTT_HOST=mosquitto`
- `MQTT_PORT=1883`
- `MQTT_HOST_PORT=1885`
- `INFLUX_URL=http://influxdb:8086`
- `INFLUX_BUCKET=iot_dados`
- `GRAFANA_PORT=3001`

## Como executar

### Pré-requisitos

- Docker Desktop em execução
- Docker Compose disponível

### Arranque normal

```powershell
docker compose up --build
```

### Recriar tudo

```powershell
docker compose down
docker compose up --build --force-recreate
```

### Ver estado

```powershell
docker compose ps
```

### Ver logs

```powershell
docker compose logs -f
```

Ou por serviço:

```powershell
docker compose logs -f modbus_server
docker compose logs -f modbus_client
docker compose logs -f influxdb_writer
docker compose logs -f mosquitto
docker compose logs -f influxdb
docker compose logs -f grafana
```

## Como parar

```powershell
docker compose down
```

## Testes unitários

O projeto inclui testes unitários com `pytest` para:
- conversão de valores do simulador para registos Modbus
- parsing de registos Modbus no cliente
- validação de leituras inválidas
- construção do ponto enviado para o InfluxDB

Instalar dependências de teste:

```powershell
pip install -r requirements-dev.txt
```

Executar:

```powershell
pytest
```

Estado atual da suíte:

```text
6 passed
```

## Acesso aos serviços

### InfluxDB

URL:

```text
http://localhost:8086
```

Credenciais:
- username: `admin`
- password: `password123`
- token: `meu-token-influx`
- organization: `minha-org`
- bucket: `iot_dados`

### Grafana

URL:

```text
http://localhost:3001
```

Credenciais:
- username: `admin`
- password: `admin123`

Ao arrancar, o Grafana já deve mostrar:
- datasource `InfluxDB-IoT`
- dashboard `IoT Industrial Overview`

## Como validar o funcionamento

### 1. Servidor Modbus

Logs esperados:

```text
[IDLE] T=22.55C P=5.41bar ...
FSM: IDLE -> WARMING
FSM: RUNNING -> ERROR [alarm=OVERPRESSURE]
```

### 2. Cliente Modbus

Logs esperados:

```text
MQTT ligado a mosquitto:1883
[RUNNING] T=62.12C P=12.03bar ...
ALARME ATIVO: OVERPRESSURE (2)
```

### 3. Persistência no InfluxDB

Logs esperados:

```text
Persistido no InfluxDB: T=62.12 P=12.03 Estado=RUNNING Alarm=OK
Persistido no InfluxDB: T=57.13 P=14.05 Estado=ERROR Alarm=OVERPRESSURE
```

## Query de exemplo no InfluxDB

```flux
from(bucket: "iot_dados")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "machine_metrics")
```

## Pipeline resumida

1. O `modbus_server` gera os dados industriais simulados.
2. O `modbus_client` lê os registos via Modbus TCP.
3. O `modbus_client` publica os dados no broker MQTT.
4. O `influxdb_writer` subscreve o tópico MQTT.
5. O `influxdb_writer` grava os dados no InfluxDB.
6. O `grafana` consome os dados do InfluxDB para visualização.

## Tecnologias usadas

- Python 3.11
- `pymodbus`
- `paho-mqtt`
- `influxdb-client`
- Docker
- Docker Compose
- Eclipse Mosquitto
- InfluxDB 2.7
- Grafana 10.4
- Pytest

## Resultado

O projeto encontra-se funcional com:
- simulação Modbus ativa
- leitura periódica no cliente
- publicação MQTT
- persistência no InfluxDB
- dashboard no Grafana
- testes unitários básicos a passar

Projeto desenvolvido para trabalho prático de IoT industrial.
