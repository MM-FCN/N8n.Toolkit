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

**运行与测试**

- **启动服务（开发，带热重载）**: 在项目根目录运行：

```bash
py -m uvicorn main:app --reload
# 或（如果在 Unix 系统或已设置 python 到 python 命令）：
# python -m uvicorn main:app --reload
```

- **停止服务**: 在运行 uvicorn 的终端中按 `Ctrl+C`，或在另一个终端杀掉进程：

```powershell
# 找到进程并杀掉（Windows PowerShell）
#Get-Process -Name python | Where-Object { $_.Path -like '*uvicorn*' } | Stop-Process
# 或者（更简单但会结束所有 python 进程）：
taskkill /IM python.exe /F
```

- **运行单个测试脚本**: 把 `run_eml_test.py`、`run_eml_summary.py` 或 `test_request.py` 中的 `url` 设置为目标地址（例如 `http://szh2vm0372.apac.bosch.com:8000/parse-eml`），然后运行：

```bash
py run_eml_test.py
py run_eml_summary.py
py test_request.py
```

- **说明**: 这些测试脚本会读取本地 `.eml` 文件并将其 base64 编码后 POST 到 `/parse-eml`，响应会打印到控制台。
