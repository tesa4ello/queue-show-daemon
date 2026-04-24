# ami/parser.py
import re
from typing import Optional, Dict, List
from logger import setup_logger

log = setup_logger("ami.parser")

class AMIResponse:
    def __init__(self, success: bool, response_type: str, message: str,
                 action_id: Optional[str] = None, headers: Optional[Dict] = None,
                 output_lines: Optional[List[str]] = None):
        self.success = success
        self.response_type = response_type
        self.message = message
        self.action_id = action_id
        self.headers = headers or {}
        self.output_lines = output_lines or []

def parse_rawman_response(raw: bytes) -> AMIResponse:
    text = raw.decode('utf-8', errors='replace').strip()
    if not text:
        return AMIResponse(False, "Empty", "No response")

    lines = text.splitlines()
    headers = {}
    output_lines = []
    response_type = None
    message = ""
    action_id = None
    in_output = False

    for line in lines:
        line = line.strip()
        if not line: continue

        if in_output:
            output_lines.append(line)
            continue

        if ':' in line:
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            headers[key] = val
            lk = key.lower()
            if lk == 'response': response_type = val
            elif lk == 'message': message = val
            elif lk == 'actionid': action_id = val
            if lk == 'response' and val.lower() == 'follows':
                in_output = True
        elif response_type and response_type.lower() in ('success', 'follows') and 'command output follows' in message.lower():
            output_lines.append(line)

    cleaned = []
    for ln in output_lines:
        if ln.startswith("Output: "):
            cleaned.append(ln[8:])
        elif ln.startswith("Output:"):
            cleaned.append(ln[7:].strip())
        else:
            cleaned.append(ln)

    success = response_type in ('Success', 'Follows', 'Goodbye')
    return AMIResponse(success, response_type or "Unknown", message, action_id, headers, cleaned)

def parse_agents(raw_lines: List[str]) -> List[Dict]:
    seen_ids = set()
    result = []
    for line in raw_lines:
        if "has taken" not in line.lower():
            continue
        m = re.match(r"^(\d+)", line)
        if not m: continue

        low = line.lower()
        
        # Точное определение состояния телефона (игнорирует "ringinuse")
        if "(not in use)" in low:
            phone_state = "not_in_use"
        elif "(ring)" in low or "(ringing)" in low:
            phone_state = "ringing"
        else:
            phone_state = "used"  # (in use), (busy), (unavailable) и т.д.

        agent = {
            "id": m.group(1),
            "member": "paused" if "paused" in low else "online",
            "phone": phone_state
        }
        if agent["id"] not in seen_ids:
            seen_ids.add(agent["id"])
            result.append(agent)
    return result
