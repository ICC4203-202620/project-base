from sqlalchemy import Column, DateTime, Index, MetaData, Numeric, String, Table, Uuid, text

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

cuisine_styles = Table(
    "cuisine_styles",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("slug", String(64), nullable=False),
    Column("name", String(80), nullable=False),
)

Index("uq_cuisine_styles_slug", cuisine_styles.c.slug, unique=True)

restaurants = Table(
    "restaurants",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("normalized_name", String(240), nullable=False),
    Column("address", String(255), nullable=False),
    Column("normalized_address", String(510), nullable=False),
    Column("identity_key", String(64), nullable=False),
    Column("latitude", Numeric(8, 6), nullable=False),
    Column("longitude", Numeric(9, 6), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

Index(
    "uq_restaurants_identity_key",
    restaurants.c.identity_key,
    unique=True,
)
Index(
    "ix_restaurants_normalized_name_id",
    restaurants.c.normalized_name,
    restaurants.c.id,
)

restaurant_cuisine_styles = Table(
    "restaurant_cuisine_styles",
    metadata,
    # DSQL does not support foreign keys. Services preserve both relationships
    # explicitly and delete associations before their restaurant.
    Column("restaurant_id", Uuid(as_uuid=True), primary_key=True),
    Column("cuisine_style_id", Uuid(as_uuid=True), primary_key=True),
)

Index(
    "ix_restaurant_cuisine_styles_cuisine_style_id",
    restaurant_cuisine_styles.c.cuisine_style_id,
)
