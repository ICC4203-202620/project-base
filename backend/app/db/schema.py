from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    MetaData,
    Numeric,
    SmallInteger,
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
# The map asks "what is inside this rectangle". Plain comparisons over these
# two columns keep the question answerable without PostGIS, which Aurora DSQL
# does not offer.
Index(
    "ix_restaurants_location",
    restaurants.c.latitude,
    restaurants.c.longitude,
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
    # A photograph is published activity in its own right, so its visibility
    # is its own and not deduced from a review it may not have.
    Column("visibility", String(16), nullable=False),
    # dish, menu or venue. Only dish is accepted until épica 9.
    Column("kind", String(16), nullable=False),
    # Which dish this is, for a photograph of one. Null for a menu or a venue.
    Column("dish_name", String(120), nullable=True),
    # Its search form, so photographs of the same dish group together whether
    # or not whoever typed them used the accents.
    Column("search_dish_name", String(240), nullable=True),
    # Optional text the interface can use as the alternative text of the image.
    Column("caption", String(500), nullable=True),
    # Identifies the act of publishing when it carried more than one
    # photograph. Null for one published on its own. The client generates it.
    Column("upload_group", Uuid(as_uuid=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Index("uq_photos_storage_key", photos.c.storage_key, unique=True)
Index("ix_photos_author_id", photos.c.author_id)
Index(
    "ix_photos_restaurant_created_id",
    photos.c.restaurant_id,
    photos.c.created_at,
    photos.c.id,
)
Index(
    "ix_photos_restaurant_dish",
    photos.c.restaurant_id,
    photos.c.search_dish_name,
)
Index("ix_photos_upload_group", photos.c.upload_group)

evaluations = Table(
    "evaluations",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    # Aurora DSQL does not support foreign keys. The service checks the
    # restaurant and the photographs in the transaction that writes the rows.
    Column("author_id", Uuid(as_uuid=True), nullable=False),
    Column("restaurant_id", Uuid(as_uuid=True), nullable=False),
    Column("comment", String(2000), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# One evaluation per person and restaurant. Without it, one person could move
# the average of a restaurant as many times as they liked.
Index(
    "uq_evaluations_author_restaurant",
    evaluations.c.author_id,
    evaluations.c.restaurant_id,
    unique=True,
)
Index(
    "ix_evaluations_restaurant_visibility_created",
    evaluations.c.restaurant_id,
    evaluations.c.visibility,
    evaluations.c.created_at,
)
Index("ix_evaluations_author_created_id", evaluations.c.author_id, evaluations.c.created_at)

evaluation_ratings = Table(
    "evaluation_ratings",
    metadata,
    Column("evaluation_id", Uuid(as_uuid=True), primary_key=True),
    # A row per criterion rather than a column per criterion: adding one is an
    # entry in the catalogue instead of a schema migration.
    Column("criterion", String(64), primary_key=True),
    Column("rating", SmallInteger(), nullable=False),
    CheckConstraint("rating BETWEEN 1 AND 5", name="ck_evaluation_ratings_range"),
)

evaluation_photos = Table(
    "evaluation_photos",
    metadata,
    Column("evaluation_id", Uuid(as_uuid=True), primary_key=True),
    Column("photo_id", Uuid(as_uuid=True), primary_key=True),
)

Index("ix_evaluation_photos_photo_id", evaluation_photos.c.photo_id)

visits = Table(
    "visits",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    # Aurora DSQL does not support foreign keys. The service checks that the
    # restaurant exists in the same transaction that persists the visit.
    Column("author_id", Uuid(as_uuid=True), nullable=False),
    Column("restaurant_id", Uuid(as_uuid=True), nullable=False),
    # When the person was there, which they report and may be in the past.
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("visibility", String(16), nullable=False),
    # When it was published, which is what reaches their followers.
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Index("ix_visits_author_occurred_id", visits.c.author_id, visits.c.occurred_at, visits.c.id)
Index(
    "ix_visits_restaurant_occurred_id",
    visits.c.restaurant_id,
    visits.c.occurred_at,
    visits.c.id,
)
Index("ix_visits_visibility_created_id", visits.c.visibility, visits.c.created_at, visits.c.id)
# The restaurant page groups the public visits of the people the viewer
# follows. Reading them from this index alone keeps that block from scanning
# the whole history of a busy restaurant.
Index(
    "ix_visits_restaurant_public_author",
    visits.c.restaurant_id,
    visits.c.visibility,
    visits.c.author_id,
    visits.c.occurred_at,
)

reviews = Table(
    "reviews",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("author_id", Uuid(as_uuid=True), nullable=False),
    Column("restaurant_id", Uuid(as_uuid=True), nullable=False),
    Column("photo_id", Uuid(as_uuid=True), nullable=False),
    # The dish lives on the photograph. Keeping it in two tables would
    # guarantee that at some point they disagree.
    # One to five, the same scale the evaluation criteria of épica 11 use, so
    # the interface presents one kind of control and both numbers read
    # together without translation.
    Column("rating", SmallInteger(), nullable=False),
    Column("text", String(2000), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating_range"),
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
