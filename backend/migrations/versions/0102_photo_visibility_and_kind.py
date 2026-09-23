"""Give a photograph its own visibility and kind.

Until now a photograph existed only as part of a review and borrowed its
visibility from it. That stops working the moment a photograph is published
without a review, which is what épica 8 introduces, and an inner join against
reviews in the gallery would have to be undone then. The kind travels in the
same migration because both are properties of the photograph and splitting
them would backfill the same table twice.
"""

import sqlalchemy as sa
from alembic import op

revision = "0102_photo_visibility_and_kind"
down_revision = "0101_index_restaurant_location"
branch_labels = None
depends_on = None

DISH = "dish"
PUBLIC = "public"

photos = sa.table(
    "photos",
    sa.column("id", sa.Uuid()),
    sa.column("visibility", sa.String()),
    sa.column("kind", sa.String()),
)
reviews = sa.table(
    "reviews",
    sa.column("photo_id", sa.Uuid()),
    sa.column("visibility", sa.String()),
)


def upgrade():
    op.add_column("photos", sa.Column("visibility", sa.String(length=16), nullable=True))
    op.add_column("photos", sa.Column("kind", sa.String(length=16), nullable=True))

    connection = op.get_bind()
    # Every photograph that exists today belongs to exactly one review, whose
    # visibility is the one it was published under.
    connection.execute(
        photos.update()
        .where(photos.c.id == reviews.c.photo_id)
        .values(visibility=reviews.c.visibility, kind=DISH)
    )
    # Any photograph without a review would be unreachable today, but a row is
    # cheaper to protect than to explain.
    connection.execute(
        photos.update()
        .where(photos.c.visibility.is_(None))
        .values(visibility=PUBLIC, kind=DISH)
    )

    op.alter_column("photos", "visibility", nullable=False)
    op.alter_column("photos", "kind", nullable=False)

    op.create_index(
        "ix_photos_restaurant_created_id",
        "photos",
        ["restaurant_id", "created_at", "id"],
    )
    # Covered by the composite index above, which starts with the same column.
    op.drop_index("ix_photos_restaurant_id", table_name="photos")


def downgrade():
    op.create_index("ix_photos_restaurant_id", "photos", ["restaurant_id"])
    op.drop_index("ix_photos_restaurant_created_id", table_name="photos")
    op.drop_column("photos", "kind")
    op.drop_column("photos", "visibility")
