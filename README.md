# EmailParser FastAPI

轻量的 FastAPI 服务，用于解析来自 n8n 或其它来源的 base64 编码的 `.eml` 数据。

运行：

```bash
pip install -r requirements.txt
uvicorn source.main:app --reload
```

示例请求（POST /api/parse-eml）：

```json
{
  "eml_payload": "<base64-encoded-eml>"
}
```

## RabbitMQ 消息发送

`POST /api/send-mq` 用于将业务消息发布到 RabbitMQ。`category` 支持整数或字符串，`content` 必须是 JSON 字符串；服务会校验并发布包含 `category` 和解析后内容的 JSON 消息，并根据 `category` 从受控映射中选择 Routing Key。数字和对应的数字字符串使用同一映射，例如 `9` 与 `"9"` 都匹配 `CategoryIds` 中的 `9`。

```json
{
  "category": "9",
  "content": "{\"orderId\":\"123\",\"amount\":100}"
}
```

成功时返回：

```json
{
  "status": "success",
  "message": "Message published"
}
```

在 `appsettings.json` 或同名环境变量中配置以下值；环境变量优先：

| 配置项 | 说明 |
| --- | --- |
| `RabbitMqUrl` | AMQP 连接 URL，例如 `amqp://user:password@host:5672/%2F`。生产环境建议仅以环境变量提供。 |
| `RabbitMqExchangeName` | 要发布到的 Exchange 名称。 |
| `RabbitMqExchangeType` | `direct` 或 `topic`。 |
| `RabbitMqRouteKeyCategoryMap` | 路由映射数组；每项包含 `RouteKey` 和 `CategoryIds`。类别可为整数或字符串，且在整个数组中必须唯一。环境变量值应为 JSON 数组字符串。 |

例如，`[{"RouteKey":"waybill.sea.crawl","CategoryIds":[9,10]}]` 会将类别 `"9"` 和 `"10"` 的消息发布到 `waybill.sea.crawl`。未配置映射的 `category` 将返回 HTTP 422。

服务在每次发送前声明 durable Exchange；Exchange 不存在时会创建。服务不会创建队列或绑定关系，RabbitMQ 管理员必须预先配置目标队列绑定，并为服务账户授权连接、声明 Exchange 与发布消息。密码中的 `@`、`:`、`/`、`!` 等 URL 保留字符必须进行百分号编码；不要提交生产 RabbitMQ URL 或凭据到仓库。

可选查询参数：
- `include_attachments` (bool): 是否在返回中包含附件的 base64 数据，默认 `false`。

**运行与测试**

- **启动服务（开发，带热重载）**: 在项目根目录运行：

```bash
py -m uvicorn source.main:app --reload
# 或（如果在 Unix 系统或已设置 python 到 python 命令）：
# python -m uvicorn source.main:app --reload
```

- **停止服务**: 在运行 uvicorn 的终端中按 `Ctrl+C`，或在另一个终端杀掉进程：

```powershell
# 找到进程并杀掉（Windows PowerShell）
#Get-Process -Name python | Where-Object { $_.Path -like '*uvicorn*' } | Stop-Process
# 或者（更简单但会结束所有 python 进程）：
taskkill /IM python.exe /F
```

- **运行单个测试脚本**: 把 `run_eml_test.py`、`run_eml_summary.py` 或 `test_request.py` 中的 `url` 设置为目标地址（例如 `http://szh2vm0372.apac.bosch.com:8000/api/parse-eml`），然后运行：

```bash
py run_eml_test.py
py run_eml_summary.py
py test_request.py
```

- **说明**: 这些测试脚本会读取本地 `.eml` 文件并将其 base64 编码后 POST 到 `/api/parse-eml`，响应会打印到控制台。