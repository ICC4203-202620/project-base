"""Index the coordinates so a map rectangle does not scan the catalogue."""

from alembic import op

revision = "0101_index_restaurant_location"
down_revision = "0100_add_restaurant_search_name"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_restaurants_location", "restaurants", ["latitude", "longitude"])


def downgrade():
    op.drop_index("ix_restaurants_location", table_name="restaurants")
