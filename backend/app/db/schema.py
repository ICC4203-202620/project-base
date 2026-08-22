from sqlalchemy import Column, DateTime, Index, MetaData, String, Table, Uuid, text

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("handle", String(64), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("nationality", String(80), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    # Aurora DSQL's SQLAlchemy adapter omits foreign keys. The application
    # verifies this relationship when authenticating a session.
    Column("user_id", Uuid(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)

Index("ix_auth_sessions_user_id", auth_sessions.c.user_id)
Index("ix_auth_sessions_expires_at", auth_sessions.c.expires_at)
