"""The conversation around a photograph."""

import sqlalchemy as sa
from alembic import op

revision = "0109_create_comments"
down_revision = "0108_index_visits_by_visitor"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        # Null for a comment, set for a reply, and never pointing at another
        # reply: the thread has two levels.
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # The conversation of a photograph, and the replies inside one comment.
    op.create_index("ix_comments_photo_created_id", "comments", ["photo_id", "created_at", "id"])
    op.create_index("ix_comments_parent_created_id", "comments", ["parent_id", "created_at", "id"])


def downgrade():
    op.drop_index("ix_comments_parent_created_id", table_name="comments")
    op.drop_index("ix_comments_photo_created_id", table_name="comments")
    op.drop_table("comments")
