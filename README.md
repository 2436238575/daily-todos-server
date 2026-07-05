# DailyTodo Server

DailyTodo Server 是 DailyTodo 的 HTTP 同步后端。服务端负责账号认证、刷新令牌管理、任务和每日模板项的增量同步，以及冲突记录；冲突的最终选择由客户端冲突中心提交。

## 当前能力

- FastAPI HTTP API。
- PostgreSQL 持久化，SQLAlchemy ORM，Alembic 迁移。
- 管理员 CLI 创建账号，不开放公开注册。
- Argon2id 密码哈希。
- Access token 加签，refresh token 仅存 SHA-256 hash。
- 任务和每日模板项按 `server_version` 增量同步。
- 不做静默最后写入覆盖；版本不一致时生成冲突记录。
- 登录和刷新接口带应用内轻量限流。

## 技术栈

- Python 3.11+
- uv
- FastAPI
- SQLAlchemy
- Alembic
- psycopg
- Pydantic Settings
- argon2-cffi
- pytest

## 快速开始

安装依赖：

```bash
uv sync --extra dev
```

准备环境变量：

```bash
cp .env.example .env
```

至少需要配置：

```bash
DAILYTODO_DATABASE_URL=postgresql://daily-todos:change-me@127.0.0.1:5435/daily-todos
DAILYTODO_SECRET_KEY=replace-with-a-long-random-secret
DAILYTODO_BIND_HOST=127.0.0.1
DAILYTODO_BIND_PORT=8080
```

初始化数据库：

```bash
uv run alembic upgrade head
```

创建第一个用户：

```bash
uv run dailytodo-user create alice
```

启动开发服务：

```bash
uv run uvicorn dailytodo_server.main:app --host "$DAILYTODO_BIND_HOST" --port "$DAILYTODO_BIND_PORT"
```

健康检查：

```bash
curl http://127.0.0.1:8080/healthz
```

## 环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DAILYTODO_DATABASE_URL` | 数据库连接 URL；支持 `postgresql://...` 和 `postgresql+psycopg://...` | `postgresql+psycopg://dailytodo:change-me@127.0.0.1:5432/dailytodo` |
| `DAILYTODO_SECRET_KEY` | Access token 签名密钥；生产环境必须替换为长随机值 | `dev-insecure-secret-change-me` |
| `DAILYTODO_BIND_HOST` | uvicorn 监听地址 | `127.0.0.1` |
| `DAILYTODO_BIND_PORT` | uvicorn 监听端口 | `8080` |
| `DAILYTODO_ACCESS_TOKEN_MINUTES` | Access token 有效分钟数 | `15` |
| `DAILYTODO_REFRESH_TOKEN_DAYS` | Refresh token 有效天数 | `30` |
| `DAILYTODO_AUTH_RATE_LIMIT_REQUESTS` | 登录/刷新限流窗口内允许次数；小于等于 0 表示关闭 | `20` |
| `DAILYTODO_AUTH_RATE_LIMIT_WINDOW_SECONDS` | 登录/刷新限流窗口秒数 | `60` |

## 数据库

新环境使用 Alembic：

```bash
uv run alembic upgrade head
```

测试库需要清空重建时可以执行：

```bash
uv run dailytodo-user reset-db --yes
```

`reset-db --yes` 会删除并重建所有 DailyTodo Server 表，只用于开发或测试数据库。

## 管理员 CLI

```bash
uv run dailytodo-user init-db
uv run dailytodo-user reset-db --yes
uv run dailytodo-user create alice
uv run dailytodo-user create alice --password "change-me"
uv run dailytodo-user list
uv run dailytodo-user list --include-disabled
uv run dailytodo-user disable alice
uv run dailytodo-user enable alice
```

生产环境建议省略 `--password`，让命令行安全提示输入密码，避免密码进入 shell history。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | 健康检查 |
| `POST` | `/v1/auth/login` | 用户名密码登录 |
| `POST` | `/v1/auth/refresh` | 使用 refresh token 换新 token |
| `POST` | `/v1/auth/logout` | 注销 refresh token |
| `GET` | `/v1/sync/pull?since=<server_version>` | 拉取增量变更和未解决冲突 |
| `POST` | `/v1/sync/push` | 推送任务和模板项变更 |
| `POST` | `/v1/sync/resolve` | 解决冲突 |

除登录和刷新外，业务接口需要：

```http
Authorization: Bearer <access_token>
```

## 请求示例

登录：

```bash
curl -X POST http://127.0.0.1:8080/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret","device_name":"desktop"}'
```

推送任务和每日模板项：

```bash
curl -X POST http://127.0.0.1:8080/v1/sync/push \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {
        "id": "33333333-4444-4555-8666-777777777777",
        "base_version": 0,
        "content": "整理今日事项",
        "target_date": "2026-07-05",
        "completed": false,
        "sort_order": 1,
        "deleted": false
      }
    ],
    "template_items": [
      {
        "id": "44444444-5555-4666-8777-888888888888",
        "base_version": 0,
        "content": "晨间回顾",
        "sort_order": 1,
        "deleted": false
      }
    ]
  }'
```

拉取增量：

```bash
curl "http://127.0.0.1:8080/v1/sync/pull?since=0" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

解决冲突：

```bash
curl -X POST http://127.0.0.1:8080/v1/sync/resolve \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resolutions": [
      {
        "conflict_id": "conflict-uuid",
        "choice": "merged",
        "merged_payload": {
          "content": "合并后的内容",
          "target_date": "2026-07-05",
          "completed": false,
          "sort_order": 1,
          "deleted": false
        }
      }
    ]
  }'
```

`choice` 可选：

- `local`：接受冲突记录中的客户端版本。
- `remote`：保留服务端当前版本。
- `merged`：使用 `merged_payload`。

## 同步语义

- 服务端为已提交变更分配单调递增的 `server_version`。
- 客户端推送每条记录时必须携带自己的 `base_version`。
- 如果服务端当前记录版本等于 `base_version`，变更会被接受。
- 如果服务端当前记录版本已经变化，服务端不会自动覆盖，而是创建冲突记录。
- 删除使用 tombstone：记录保留，`deleted=true`，方便其他客户端观察删除事件。
- `pull` 返回自 `since` 之后变化过的任务、模板项，以及当前未解决冲突。

## 测试

```bash
uv run pytest
```

当前测试覆盖：

- 登录、刷新、登出。
- 任务 push/pull、版本冲突和解决。
- 每日模板项同步。

在部分 WSL 沙盒环境中，`uv` 默认缓存目录可能不可写，可以改用 `/tmp`：

```bash
uv --cache-dir /tmp/dailytodo-uv-cache sync --extra dev
uv --cache-dir /tmp/dailytodo-uv-cache run pytest
```

## 部署

服务预期运行在雷池反向代理后面：

- uvicorn 绑定内网地址，不直接暴露公网。
- PostgreSQL 只监听 localhost 或私有网络。
- `/etc/dailytodo/server.env` 权限设置为 `600`。
- 反向代理层也应配置登录和刷新接口限流。

systemd 示例见 [docs/systemd.md](docs/systemd.md)。

## 安全注意事项

- 生产环境必须设置强随机 `DAILYTODO_SECRET_KEY`。
- 不要记录密码、refresh token 或完整 `Authorization` 头。
- refresh token 原文只返回给客户端一次，数据库中仅保存 hash。
- 管理员创建账号，不提供公开注册入口。
- `reset-db --yes` 只允许用于开发或测试数据库。

## 设计文档

同步设计见 [docs/sync-design.md](docs/sync-design.md)。
