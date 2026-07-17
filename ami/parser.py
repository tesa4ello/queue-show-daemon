# ami/parser.py
import re
from typing import Optional, Dict, List
from logger import setup_logger

log = setup_logger("ami.parser")


class AMIResponse:
    def __init__(self, success: bool, response_type: str, message: str,
                 action_id: Optional[str] = None, headers: Optional[Dict] = None,
                 events: Optional[List[Dict]] = None):
        self.success = success
        self.response_type = response_type
        self.message = message
        self.action_id = action_id
        # headers -> поля первого блока ответа (Response/Message/ActionID/Ping/...)
        self.headers = headers or {}
        # events -> последующие блоки-события (QueueMember, QueueEntry, ...)
        self.events = events or []


def _parse_blocks(text: str) -> List[Dict[str, str]]:
    """Разбирает ответ rawman в список блоков.

    rawman/HTTP возвращает заголовок ответа и все сгенерированные действием
    события в одном HTTP-ответе; блоки разделяются пустой строкой, внутри блока —
    строки вида ``key: value``.
    """
    blocks: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    for line in text.splitlines():
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = {}
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            current[key.strip()] = val.strip()
    if current:
        blocks.append(current)
    return blocks


def parse_rawman_response(raw: bytes) -> AMIResponse:
    text = raw.decode("utf-8", errors="replace")
    blocks = _parse_blocks(text)
    if not blocks:
        return AMIResponse(False, "Empty", "No response")

    head = blocks[0]
    lower = {k.lower(): v for k, v in head.items()}  # регистронезависимый доступ
    response_type = lower.get("response", "Unknown")
    message = lower.get("message", "")
    action_id = lower.get("actionid")

    events = blocks[1:]
    success = response_type in ("Success", "Follows", "Goodbye", "Pong")
    return AMIResponse(success, response_type, message, action_id, head, events)


# AST device state (числовой Status в событии QueueMember) -> состояние телефона.
# 1 = Not in use, 6 = Ringing; всё остальное (in use / busy / unavailable /
# ringinuse / onhold / ...) считаем "used" — как и прежняя текстовая логика,
# где ringinuse НЕ считался звонком.
_STATUS_MAP = {
    "1": "not_in_use",
    "6": "ringing",
}


def parse_queue_members(events: List[Dict]) -> List[Dict]:
    """Извлекает агентов из событий QueueMember (ответ на действие QueueStatus)."""
    seen_ids = set()
    result: List[Dict] = []
    for ev in events:
        if ev.get("Event") != "QueueMember":
            continue

        # Name = membername. Прежде id брался как ведущие цифры строки `queue show`,
        # а она начинается именно с membername -> поведение сохранено.
        name = ev.get("Name", "").strip()
        m = re.match(r"^(\d+)", name)
        if not m:
            continue
        agent_id = m.group(1)
        if agent_id in seen_ids:
            continue
        seen_ids.add(agent_id)

        phone_state = _STATUS_MAP.get(ev.get("Status", ""), "used")
        paused = ev.get("Paused", "0") == "1"

        result.append({
            "id": agent_id,
            "member": "paused" if paused else "online",
            "phone": phone_state,
        })
    return result
