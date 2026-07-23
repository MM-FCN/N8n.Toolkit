"""
email_parse.py

基础的 Email Parse 接口模板。
"""
from typing import Dict, Any, Optional, List
import base64
import email
from email import policy
from email.header import decode_header
from email.utils import getaddresses, parsedate_to_datetime


def _decode_header_str(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parts = decode_header(value)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(enc or "utf-8", errors="replace"))
            except Exception:
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_addresses(header_value: Optional[str]) -> List[Dict[str, str]]:
    if not header_value:
        return []
    addrs = getaddresses([header_value])
    return [{"name": _decode_header_str(name), "email": addr} for name, addr in addrs]


class EmailParser:
    """Email parsing utility. Provides methods to parse EML from bytes or base64."""

    def parse_from_bytes(self, eml_bytes: bytes) -> Dict[str, Any]:
        msg = email.message_from_bytes(eml_bytes, policy=policy.default)

        subject = _decode_header_str(msg["subject"]) or None
        from_header = _decode_header_str(msg["from"]) or None
        to_header = _decode_header_str(msg["to"]) or None

        date_iso = None
        try:
            if msg["date"]:
                date_iso = parsedate_to_datetime(msg["date"]).isoformat()
        except Exception:
            date_iso = str(msg["date"]) if msg["date"] else None

        result: Dict[str, Any] = {
            "subject": subject,
            "from": _extract_addresses(from_header) if from_header else [],
            "to": _extract_addresses(to_header) if to_header else [],
            "date": date_iso,
            "body_text": "",
            "body_html": "",
            "attachments": [],
        }

        def _to_bytes(payload, charset: Optional[str]):
            if isinstance(payload, bytes):
                return payload
            if isinstance(payload, str):
                return payload.encode(charset or "utf-8", errors="replace")
            return b""

        if msg.is_multipart():
            for part in msg.iter_parts():
                content_type = part.get_content_type()
                disposition = part.get_content_disposition()

                if disposition is None:
                    try:
                        payload = part.get_content()
                        if content_type == "text/plain" and not result["body_text"]:
                            result["body_text"] = payload
                        elif content_type == "text/html" and not result["body_html"]:
                            result["body_html"] = payload
                    except Exception:
                        pass

                if disposition == "attachment" or part.get_filename():
                    filename = _decode_header_str(part.get_filename())
                    payload = part.get_content()
                    payload_bytes = _to_bytes(payload, part.get_content_charset())
                    size = len(payload_bytes)
                    data_b64 = base64.b64encode(payload_bytes).decode("utf-8") if size > 0 else None
                    result["attachments"].append({
                        "filename": filename,
                        "content_type": content_type,
                        "size": size,
                        "data_b64": data_b64,
                    })
        else:
            try:
                payload = msg.get_content()
                if isinstance(payload, str):
                    result["body_text"] = payload
                else:
                    result["body_text"] = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                result["body_text"] = ""

        return result

    def parse_from_b64(self, b64_payload: str) -> Dict[str, Any]:
        eml_bytes = base64.b64decode(b64_payload)
        return self.parse_from_bytes(eml_bytes)


def parse_eml_b64(b64_payload: str) -> Dict[str, Any]:
    parser = EmailParser()
    return parser.parse_from_b64(b64_payload)
