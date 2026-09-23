"""Record that a person was at a restaurant."""

import sqlalchemy as sa
from alembic import op

revision = "0103_create_visits"
down_revision = "0102_photo_visibility_and_kind"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "visits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # The profile reads a person's chronology, the restaurant page reads who
    # was there, and the feed reads what was published and when.
    op.create_index(
        "ix_visits_author_occurred_id", "visits", ["author_id", "occurred_at", "id"]
    )
    op.create_index(
        "ix_visits_restaurant_occurred_id", "visits", ["restaurant_id", "occurred_at", "id"]
    )
    op.create_index(
        "ix_visits_visibility_created_id", "visits", ["visibility", "created_at", "id"]
    )


def downgrade():
    op.drop_index("ix_visits_visibility_created_id", table_name="visits")
    op.drop_index("ix_visits_restaurant_occurred_id", table_name="visits")
    op.drop_index("ix_visits_author_occurred_id", table_name="visits")
    op.drop_table("visits")
