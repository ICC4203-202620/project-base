"""Add the diacritic-free search form of a restaurant name.

The normalization is copied here on purpose instead of imported from
``app.services.restaurants``. A migration records what was computed when it
ran; importing application code would let a later change to that function
silently redefine history.
"""

import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0100_add_restaurant_search_name"
down_revision = "0005_create_follows"
branch_labels = None
depends_on = None

restaurants = sa.table(
    "restaurants",
    sa.column("id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("search_name", sa.String()),
)


def _search_form(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(unicodedata.normalize("NFKC", without_marks).split()).casefold()


def upgrade():
    op.add_column("restaurants", sa.Column("search_name", sa.String(length=240), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.select(restaurants.c.id, restaurants.c.name)).all()
    for row in rows:
        connection.execute(
            sa.update(restaurants)
            .where(restaurants.c.id == row.id)
            .values(search_name=_search_form(row.name))
        )

    op.alter_column("restaurants", "search_name", nullable=False)
    op.create_index("ix_restaurants_search_name_id", "restaurants", ["search_name", "id"])


def downgrade():
    op.drop_index("ix_restaurants_search_name_id", table_name="restaurants")
    op.drop_column("restaurants", "search_name")
