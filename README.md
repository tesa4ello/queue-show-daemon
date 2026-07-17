# Asterisk Queue Proxy

Небольшой HTTP-демон, который отдаёт статусы агентов очередей Asterisk в JSON.
Данные о состоянии устройства берутся из Asterisk через AMI-действие
**`QueueStatus`** (событийное, без CLI-локов, совместимо с Asterisk 13–21),
а имя/телефон/состояние агента — из таблицы MySQL `queue_agents`.

## Как это работает

```
GET /queue?queues[]=<q1>&queues[]=<q2>
  → QueueStatus по каждой очереди (AMI /rawman)  ─┐
  → SELECT ... FROM queue_agents WHERE agentid IN ─┴─→  объединённый JSON
```

Пример ответа:

```json
{
  "2001": {
    "name": "Иванов",
    "phonenum": "2001",
    "id": "2001",
    "phone": "phoneready",
    "state": "online",
    "dateofchange": "2026-01-01 10:00:00"
  }
}
```

`phone`: `phoneready` / `phoneringing` / `phonebusy`.
`state`: `online` / `busy`, а для агентов «на паузе» — значение из БД.

## Требования

- Python 3.9+
- `PyMySQL` (см. `requirements.txt`)
- Asterisk с включённым HTTP-интерфейсом менеджера (`/rawman`)
- MySQL с таблицей `queue_agents` (колонки: `agentid, state, agentphone, name, dateofchange`)

## Настройка Asterisk

`/etc/asterisk/http.conf`:

```ini
[general]
enabled=yes
bindaddr=127.0.0.1
bindport=8088
```

`/etc/asterisk/manager.conf` — для `QueueStatus` нужны права `agent`/`call`
(класс `command` больше **не** требуется):

```ini
[general]
enabled=yes
webenabled=yes          ; обязательно для /rawman
port=5038
bindaddr=127.0.0.1

[monitor]
secret=CHANGE_ME
read=agent,call,reporting
write=agent,call
```

Применить: `asterisk -rx "module reload http.conf"` и `asterisk -rx "manager reload"`.

> `agentid` в таблице `queue_agents` должен совпадать с числовым `membername`
> агента в очереди — по нему связываются данные из Asterisk и из БД.

## Установка

```bash
git clone -b claude/program-locks-compatibility-19780n \
  https://github.com/tesa4ello/queue-show-daemon.git
cd queue-show-daemon
sudo bash install.sh
```

`install.sh`:

- копирует код в `/opt/asterisk-queue-proxy`;
- ставит зависимость `PyMySQL` (через `apt` → `python3-pymysql`, иначе `pip`);
- создаёт `.env` из `.env.example` (существующий конфиг не затирает);
- генерирует и запускает systemd-юнит `asterisk-queue-proxy`.

После установки отредактируйте конфиг и перезапустите:

```bash
sudo nano /opt/asterisk-queue-proxy/.env
sudo systemctl restart asterisk-queue-proxy
```

## Конфигурация (`.env`)

| Переменная            | Назначение                         | По умолчанию   |
|-----------------------|------------------------------------|----------------|
| `APP_HOST` / `APP_PORT` | адрес HTTP-листенера              | `0.0.0.0:8080` |
| `AMI_HOST` / `AMI_PORT` | HTTP-менеджер Asterisk (`/rawman`)| `127.0.0.1:8088` |
| `AMI_USER` / `AMI_PASS` | учётка AMI                        | —              |
| `AMI_TIMEOUT`         | таймаут AMI-запроса, сек           | `10`           |
| `KEEPALIVE_INTERVAL`  | интервал keepalive/ping, сек       | `30`           |
| `MYSQL_HOST` / `MYSQL_PORT` | MySQL                         | `127.0.0.1:3306` |
| `MYSQL_USER` / `MYSQL_PASS` / `MYSQL_BASE` | доступ к БД     | —              |
| `LOG_LEVEL` / `LOG_FILE` | логирование                     | `INFO`         |

## Проверка

```bash
systemctl status asterisk-queue-proxy
journalctl -u asterisk-queue-proxy -f
curl "http://127.0.0.1:8080/queue?queues[]=sales&queues[]=support"
```

## Управление

```bash
sudo systemctl restart asterisk-queue-proxy
sudo systemctl stop asterisk-queue-proxy
sudo systemctl disable asterisk-queue-proxy
```
