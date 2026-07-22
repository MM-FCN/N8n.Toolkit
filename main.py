from fastapi import FastAPI
from pydantic import BaseModel
import base64
import email
from email import policy
from email.header import decode_header
from email.utils import getaddresses, parsedate_to_datetime
from typing import Optional, List

app = FastAPI()


class EmlRequest(BaseModel):
    eml_payload: str


def decode_header_str(value: Optional[str]) -> Optional[str]:
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


def extract_addresses(header_value: Optional[str]):
    if not header_value:
        return []
    addrs = getaddresses([header_value])
    return [{"name": decode_header_str(name), "email": addr} for name, addr in addrs]


@app.post("/parse-eml")
async def parse_eml(request: EmlRequest):
    try:
        eml_bytes = base64.b64decode(request.eml_payload)
        msg = email.message_from_bytes(eml_bytes, policy=policy.default)

        subject = decode_header_str(msg["subject"])
        from_header = decode_header_str(msg["from"]) or None
        to_header = decode_header_str(msg["to"]) or None

        # 尝试把日期解析成 ISO 格式
        date_iso = None
        try:
            if msg["date"]:
                date_iso = parsedate_to_datetime(msg["date"]).isoformat()
        except Exception:
            date_iso = str(msg["date"]) if msg["date"] else None

        result = {
            "subject": subject,
            "from": extract_addresses(from_header) if from_header else [],
            "to": extract_addresses(to_header) if to_header else [],
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
                disposition = part.get_content_disposition()  # 'attachment', 'inline', or None

                # 正文部分（优先 text/plain，再 text/html）
                if disposition is None:
                    try:
                        payload = part.get_content()
                        if content_type == "text/plain" and not result["body_text"]:
                            result["body_text"] = payload
                        elif content_type == "text/html" and not result["body_html"]:
                            result["body_html"] = payload
                    except Exception:
                        pass

                # 附件处理
                if disposition == "attachment" or part.get_filename():
                    filename = decode_header_str(part.get_filename())
                    payload = part.get_content()
                    payload_bytes = _to_bytes(payload, part.get_content_charset())
                    size = len(payload_bytes)
                    # 始终将附件内容以 base64 形式返回，客户端决定是否保存/下载
                    data_b64 = base64.b64encode(payload_bytes).decode("utf-8") if size > 0 else None
                    result["attachments"].append({
                        "filename": filename,
                        "content_type": content_type,
                        "size": size,
                        "data_b64": data_b64,
                    })
        else:
            # 非 multipart
            try:
                payload = msg.get_content()
                if isinstance(payload, str):
                    result["body_text"] = payload
                else:
                    # bytes
                    result["body_text"] = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                result["body_text"] = ""

        return {"status": "success", "data": result}

    except Exception as e:
        return {"status": "error", "message": str(e)}
