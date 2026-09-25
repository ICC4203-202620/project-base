"""Evaluate a restaurant as a whole, on several criteria."""

import sqlalchemy as sa
from alembic import op

revision = "0107_create_evaluations"
down_revision = "0106_review_rating"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("comment", sa.String(length=2000), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # One evaluation per person and restaurant, so nobody moves an average
    # as many times as they like.
    op.create_index(
        "uq_evaluations_author_restaurant",
        "evaluations",
        ["author_id", "restaurant_id"],
        unique=True,
    )
    op.create_index(
        "ix_evaluations_restaurant_visibility_created",
        "evaluations",
        ["restaurant_id", "visibility", "created_at"],
    )
    op.create_index(
        "ix_evaluations_author_created_id", "evaluations", ["author_id", "created_at"]
    )

    op.create_table(
        "evaluation_ratings",
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("criterion", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("evaluation_id", "criterion"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_evaluation_ratings_range"),
    )

    op.create_table(
        "evaluation_photos",
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("evaluation_id", "photo_id"),
    )
    op.create_index("ix_evaluation_photos_photo_id", "evaluation_photos", ["photo_id"])


def downgrade():
    op.drop_index("ix_evaluation_photos_photo_id", table_name="evaluation_photos")
    op.drop_table("evaluation_photos")
    op.drop_table("evaluation_ratings")
    op.drop_index("ix_evaluations_author_created_id", table_name="evaluations")
    op.drop_index("ix_evaluations_restaurant_visibility_created", table_name="evaluations")
    op.drop_index("uq_evaluations_author_restaurant", table_name="evaluations")
    op.drop_table("evaluations")
