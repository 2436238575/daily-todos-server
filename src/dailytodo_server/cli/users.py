"""User administration CLI."""

from __future__ import annotations

import argparse
from getpass import getpass

from sqlalchemy import select

from dailytodo_server import models
from dailytodo_server.db import create_session_factory, ensure_database_schema
from dailytodo_server.services import create_user, set_user_disabled
from dailytodo_server.settings import get_settings


def _read_password(provided: str | None) -> str:
    if provided is not None:
        return provided
    password = getpass("Password: ")
    confirm = getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("passwords do not match")
    if not password:
        raise SystemExit("password cannot be empty")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(prog="dailytodo-user")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create database tables")

    reset_parser = subparsers.add_parser("reset-db", help="Drop and recreate all database tables")
    reset_parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")

    create_parser = subparsers.add_parser("create", help="Create a username/password account")
    create_parser.add_argument("username")
    create_parser.add_argument("--password", help="Password value; omit to prompt securely")

    list_parser = subparsers.add_parser("list", help="List users")
    list_parser.add_argument("--include-disabled", action="store_true")

    disable_parser = subparsers.add_parser("disable", help="Disable a user")
    disable_parser.add_argument("username")

    enable_parser = subparsers.add_parser("enable", help="Enable a disabled user")
    enable_parser.add_argument("username")

    args = parser.parse_args()
    settings = get_settings()
    session_factory = create_session_factory(settings)

    if args.command == "init-db":
        ensure_database_schema(session_factory.kw["bind"])
        print("database tables are ready")
        return

    if args.command == "reset-db":
        if not args.yes:
            raise SystemExit("reset-db is destructive; pass --yes to confirm")
        from dailytodo_server.db import Base

        Base.metadata.drop_all(session_factory.kw["bind"])
        ensure_database_schema(session_factory.kw["bind"])
        print("database tables were reset")
        return

    if args.command == "create":
        with session_factory() as session:
            create_user(session, args.username, _read_password(args.password))
            session.commit()
        print(f"created user: {args.username}")
        return

    if args.command == "list":
        with session_factory() as session:
            query = select(models.User).order_by(models.User.username)
            if not args.include_disabled:
                query = query.where(models.User.disabled_at.is_(None))
            for user in session.scalars(query):
                suffix = " disabled" if user.disabled_at else ""
                print(f"{user.username}{suffix}")
        return

    if args.command == "disable":
        with session_factory() as session:
            set_user_disabled(session, args.username, True)
            session.commit()
        print(f"disabled user: {args.username}")
        return

    if args.command == "enable":
        with session_factory() as session:
            set_user_disabled(session, args.username, False)
            session.commit()
        print(f"enabled user: {args.username}")
        return
