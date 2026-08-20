from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid, text

metadata = MetaData()
users = Table(
    "users", metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("handle", String(64), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("nationality", String(80), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
)
