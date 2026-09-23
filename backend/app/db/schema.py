from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    MetaData,
    Numeric,
    String,
    Table,
    Uuid,
    text,
)

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

user_follows = Table(
    "user_follows",
    metadata,
    Column("follower_id", Uuid(as_uuid=True), primary_key=True),
    Column("followed_id", Uuid(as_uuid=True), primary_key=True),
    CheckConstraint("follower_id <> followed_id", name="ck_user_follows_not_self"),
)
Index("ix_user_follows_followed_id", user_follows.c.followed_id)

restaurant_follows = Table(
    "restaurant_follows",
    metadata,
    Column("user_id", Uuid(as_uuid=True), primary_key=True),
    Column("restaurant_id", Uuid(as_uuid=True), primary_key=True),
)
Index("ix_restaurant_follows_restaurant_id", restaurant_follows.c.restaurant_id)

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
    # Search form: same text without diacritics. It is a separate column and
    # not a replacement, because duplicate detection must keep telling
    # "Café Perú" and "Cafe Peru" apart while search finds them together.
    Column("search_name", String(240), nullable=False),
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
Index(
    "ix_restaurants_search_name_id",
    restaurants.c.search_name,
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

photos = Table(
    "photos",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    # Aurora DSQL does not support foreign keys. Review services validate these
    # relationships in the same transaction that persists the metadata.
    Column("author_id", Uuid(as_uuid=True), nullable=False),
    Column("restaurant_id", Uuid(as_uuid=True), nullable=False),
    Column("storage_key", String(512), nullable=False),
    Column("content_type", String(64), nullable=False),
    Column("size_bytes", BigInteger(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Index("uq_photos_storage_key", photos.c.storage_key, unique=True)
Index("ix_photos_author_id", photos.c.author_id)
Index("ix_photos_restaurant_id", photos.c.restaurant_id)

reviews = Table(
    "reviews",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("author_id", Uuid(as_uuid=True), nullable=False),
    Column("restaurant_id", Uuid(as_uuid=True), nullable=False),
    Column("photo_id", Uuid(as_uuid=True), nullable=False),
    Column("dish_name", String(120), nullable=False),
    Column("text", String(2000), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

Index("uq_reviews_photo_id", reviews.c.photo_id, unique=True)
Index("ix_reviews_author_created_id", reviews.c.author_id, reviews.c.created_at, reviews.c.id)
Index(
    "ix_reviews_restaurant_created_id",
    reviews.c.restaurant_id,
    reviews.c.created_at,
    reviews.c.id,
)
Index(
    "ix_reviews_visibility_created_id",
    reviews.c.visibility,
    reviews.c.created_at,
    reviews.c.id,
)
