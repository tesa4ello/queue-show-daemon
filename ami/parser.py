# ami/parser.py
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any
from logger import setup_logger

log = setup_logger("ami.parser")

class AMIResponse:
    """Результат парсинга XML-ответа от Asterisk mxml."""
    def __init__(self, success: bool, response_type: str, message: str, 
                 action_id: Optional[str] = None, extra: Optional[Dict] = None):
        self.success = success
        self.response_type = response_type  # Success, Error, Goodbye
        self.message = message
        self.action_id = action_id
        self.extra = extra or {}
    
    def __repr__(self):
        return f"AMIResponse({self.response_type}, {self.message})"

def parse_mxml_response(xml_raw: bytes) -> AMIResponse:
    """
    Парсит ответ вида:
    <ajax-response>
      <response type="object" id="unknown">
        <generic response="Success" message="..." actionid="..." ping="..."/>
      </response>
    </ajax-response>
    """
    try:
        root = ET.fromstring(xml_raw.decode("utf-8", errors="replace"))
        generic = root.find(".//generic")
        
        if generic is None:
            log.warning(f"Unexpected XML structure: {xml_raw[:200]}")
            return AMIResponse(False, "Unknown", "Parse error")
        
        resp_type = generic.get("response", "Unknown")
        message = generic.get("message", "")
        action_id = generic.get("actionid")
        
        # Собираем доп. атрибуты (ping, timestamp и т.д.)
        extra = {k: v for k, v in generic.attrib.items() 
                 if k not in ("response", "message", "actionid")}
        
        # Определяем успех
        success = resp_type in ("Success", "Goodbye")
        
        return AMIResponse(success, resp_type, message, action_id, extra)
        
    except ET.ParseError as e:
        log.error(f"XML parse error: {e}, raw: {xml_raw[:200]}")
        return AMIResponse(False, "ParseError", str(e))
    except Exception as e:
        log.exception(f"Unexpected error parsing AMI response")
        return AMIResponse(False, "Exception", str(e))
