# DailyTodo Sync Design

## Decisions

- The server is authoritative for committed versions, but conflicts are not auto-resolved.
- Users are created by an administrator using a CLI.
- Login uses a username and password.
- Desktop and mobile clients sync tasks and daily template items.
- The service speaks HTTP behind a LeiChi reverse proxy.

## Core Tables

- `users`: username, password hash, disabled marker, timestamps.
- `devices`: user-owned client devices with last-seen metadata.
- `refresh_tokens`: hashed refresh tokens scoped to users and devices.
- `tasks`: UUID primary identity, user owner, content, target date, completion state, sort order, delete marker, version, timestamps.
- `template_items`: UUID primary identity, user owner, content, sort order, delete marker, version, timestamps.
- `sync_events`: monotonically increasing server versions for incremental pull.

## Sync Flow

1. Client logs in and receives an access token plus a refresh token.
2. Client pulls changes since its last server version.
3. Client pushes local outbox changes with each row's `base_version`.
4. Server accepts unchanged rows and creates conflict records for rows whose server version changed.
5. Client displays conflicts in a conflict center.
6. Client submits selected local, remote, or merged values to `/v1/sync/resolve`.

## Conflict Rules

- No silent last-write-wins.
- Deleted rows remain tombstoned until all clients have had enough time to observe them.
- Reorder conflicts are resolved by choosing one complete order for the affected date or template.

## Deployment Notes

- Run under systemd with an environment file readable only by the service user.
- Bind to the private address consumed by LeiChi.
- Do not expose PostgreSQL to the public internet.
- Apply rate limits at the reverse proxy and in the app for login and refresh endpoints.

