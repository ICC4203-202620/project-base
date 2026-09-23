"""Move the dish from the review to the photograph, and add its caption.

A photograph is what gets published; the review is an opinion added on top of
it. The dish is therefore a property of the photograph, and keeping it in two
tables would guarantee that at some point they disagree.

The normalization is copied here rather than imported for the same reason as
in 0100: a migration records what was computed when it ran.
"""

import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0104_photo_dish_and_caption"
down_revision = "0103_create_visits"
branch_labels = None
depends_on = None

photos = sa.table(
    "photos",
    sa.column("id", sa.Uuid()),
    sa.column("dish_name", sa.String()),
    sa.column("search_dish_name", sa.String()),
)
reviews = sa.table(
    "reviews",
    sa.column("photo_id", sa.Uuid()),
    sa.column("dish_name", sa.String()),
)


def _search_form(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(unicodedata.normalize("NFKC", without_marks).split()).casefold()


def upgrade():
    op.add_column("photos", sa.Column("dish_name", sa.String(length=120), nullable=True))
    op.add_column("photos", sa.Column("search_dish_name", sa.String(length=240), nullable=True))
    op.add_column("photos", sa.Column("caption", sa.String(length=500), nullable=True))

    connection = op.get_bind()
    connection.execute(
        photos.update()
        .where(photos.c.id == reviews.c.photo_id)
        .values(dish_name=reviews.c.dish_name)
    )
    for row in connection.execute(
        sa.select(photos.c.id, photos.c.dish_name).where(photos.c.dish_name.is_not(None))
    ).all():
        connection.execute(
            photos.update()
            .where(photos.c.id == row.id)
            .values(search_dish_name=_search_form(row.dish_name))
        )

    op.create_index("ix_photos_restaurant_dish", "photos", ["restaurant_id", "search_dish_name"])
    op.drop_column("reviews", "dish_name")


def downgrade():
    op.add_column("reviews", sa.Column("dish_name", sa.String(length=120), nullable=True))
    connection = op.get_bind()
    connection.execute(
        reviews.update()
        .where(reviews.c.photo_id == photos.c.id)
        .values(dish_name=photos.c.dish_name)
    )
    connection.execute(reviews.update().where(reviews.c.dish_name.is_(None)).values(dish_name=""))
    op.alter_column("reviews", "dish_name", nullable=False)

    op.drop_index("ix_photos_restaurant_dish", table_name="photos")
    op.drop_column("photos", "caption")
    op.drop_column("photos", "search_dish_name")
    op.drop_column("photos", "dish_name")
