"""Group the public visits of a restaurant by who made them."""

from alembic import op

revision = "0108_index_visits_by_visitor"
down_revision = "0107_create_evaluations"
branch_labels = None
depends_on = None


def upgrade():
    # The index of #40 leads with the restaurant and then with the instant, so
    # grouping by person made the restaurant page read every visit the place
    # ever received. This one answers the block from the index.
    op.create_index(
        "ix_visits_restaurant_public_author",
        "visits",
        ["restaurant_id", "visibility", "author_id", "occurred_at"],
    )


def downgrade():
    op.drop_index("ix_visits_restaurant_public_author", table_name="visits")
