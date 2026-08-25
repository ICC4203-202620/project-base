import sqlalchemy as sa
from alembic import op

revision = "0004_create_reviews"
down_revision = "0003_create_restaurants"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "photos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_photos_storage_key", "photos", ["storage_key"], unique=True)
    op.create_index("ix_photos_author_id", "photos", ["author_id"])
    op.create_index("ix_photos_restaurant_id", "photos", ["restaurant_id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("dish_name", sa.String(120), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_reviews_photo_id", "reviews", ["photo_id"], unique=True)
    op.create_index(
        "ix_reviews_author_created_id",
        "reviews",
        ["author_id", "created_at", "id"],
    )
    op.create_index(
        "ix_reviews_restaurant_created_id",
        "reviews",
        ["restaurant_id", "created_at", "id"],
    )
    op.create_index(
        "ix_reviews_visibility_created_id",
        "reviews",
        ["visibility", "created_at", "id"],
    )


def downgrade():
    op.drop_index("ix_reviews_visibility_created_id", table_name="reviews")
    op.drop_index("ix_reviews_restaurant_created_id", table_name="reviews")
    op.drop_index("ix_reviews_author_created_id", table_name="reviews")
    op.drop_index("uq_reviews_photo_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_photos_restaurant_id", table_name="photos")
    op.drop_index("ix_photos_author_id", table_name="photos")
    op.drop_index("uq_photos_storage_key", table_name="photos")
    op.drop_table("photos")
