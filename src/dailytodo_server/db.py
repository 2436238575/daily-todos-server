"""Database engine and session helpers."""

from collections.abc import Generator

from sqlalchemy import Integer, create_engine
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import Settings


class Base(DeclarativeBase):
    pass


def create_engine_for_settings(settings: Settings):
    connect_args = {}
    database_url = settings.database_url
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(
        bind=create_engine_for_settings(settings),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_database_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    if "tasks" not in inspector.get_table_names():
        return

    column_info = {column["name"]: column for column in inspector.get_columns("tasks")}
    columns = set(column_info)
    statements: list[str] = []
    if "id" in column_info and isinstance(column_info["id"]["type"], Integer):
        statements.append("ALTER TABLE tasks ALTER COLUMN id DROP DEFAULT")
        statements.append("ALTER TABLE tasks ALTER COLUMN id TYPE VARCHAR(36) USING id::varchar")
    if "user_id" not in columns:
        statements.append("ALTER TABLE tasks ADD COLUMN user_id VARCHAR(36)")
    if "deleted_at" not in columns:
        statements.append("ALTER TABLE tasks ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE")
    if "version" not in columns:
        statements.append("ALTER TABLE tasks ADD COLUMN version INTEGER NOT NULL DEFAULT 0")
    if "is_completed" not in columns and "completed" in columns:
        statements.append("ALTER TABLE tasks RENAME COLUMN completed TO is_completed")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
