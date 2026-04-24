# ami/parser.py
import re
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List
from logger import setup_logger

log = setup_logger("ami.parser")

class AMIResponse:
    def __init__(self, success: bool, response_type: str, message: str, 
                 action_id: Optional[str] = None, extra: Optional[Dict] = None,
                 command_output: Optional[List[str]] = None):
        self.success = success
        self.response_type = response_type
        self.message = message
        self.action_id = action_id
        self.extra = extra or {}
        self.command_output = command_output or []

def parse_mxml_response(xml_raw: bytes) -> AMIResponse:
    try:
        root = ET.fromstring(xml_raw.decode("utf-8", errors="replace"))
        generic = root.find(".//generic")
        if generic is None:
            return AMIResponse(False, "Unknown", "Parse error")
        
        resp_type = generic.get("response", "Unknown")
        message = generic.get("message", "")
        action_id = generic.get("actionid")
        extra = {k: v for k, v in generic.attrib.items() 
                 if k not in ("response", "message", "actionid")}
        
        command_output = []
        for i in range(1, 50):
            key = f"output" if i == 1 else f"output-{i}"
            val = generic.get(key)
            if val is None: break
            if val.strip(): command_output.append(val.strip())
            
        return AMIResponse(resp_type in ("Success", "Goodbye"), resp_type, message, 
                           action_id, extra, command_output)
    except Exception as e:
        log.error(f"XML parse error: {e}")
        return AMIResponse(False, "Exception", str(e))

def parse_agents(raw_lines: List[str]) -> List[Dict[str, str]]:
    """Парсит вывод queue show, оставляя только агентов."""
    seen_ids = set()
    result = []
    for line in raw_lines:
        # Отсекаем строку самой очереди и заголовки
        if "has taken" not in line.lower():
            continue
        m = re.match(r"^(\d+)", line)
        if not m: continue

        low = line.lower()
        agent = {
            "id": m.group(1),
            "member": "paused" if "paused" in low else "online",
            "phone": "not_in_use" if "not in use" in low else 
                     ("ringing" if "ring" in low else "used")
        }
        if agent["id"] not in seen_ids:
            seen_ids.add(agent["id"])
            result.append(agent)
    return result
