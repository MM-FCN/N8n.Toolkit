# EmailParser FastAPI

轻量的 FastAPI 服务，用于解析来自 n8n 或其它来源的 base64 编码的 `.eml` 数据。

运行：

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

示例请求（POST /parse-eml）：

```json
{
  "eml_payload": "<base64-encoded-eml>"
}
```

可选查询参数：
- `include_attachments` (bool): 是否在返回中包含附件的 base64 数据，默认 `false`。
