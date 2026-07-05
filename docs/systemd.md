# systemd Deployment Notes

The service is intended to run behind LeiChi. Bind the app to a private address and expose only LeiChi publicly.

Example service:

```ini
[Unit]
Description=DailyTodo Server
After=network-online.target
Wants=network-online.target

[Service]
User=dailytodo
Group=dailytodo
WorkingDirectory=/opt/daily-todos-server
EnvironmentFile=/etc/dailytodo/server.env
ExecStart=/usr/bin/uv run uvicorn dailytodo_server.main:app --host ${DAILYTODO_BIND_HOST} --port ${DAILYTODO_BIND_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Set `/etc/dailytodo/server.env` permissions to `600` and keep PostgreSQL on localhost or a private network.

