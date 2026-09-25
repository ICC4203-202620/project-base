"""Give a review the rating the statement asks for.

The épica describes a review as a rating and a text since the first page, and
the table never had the number.
"""

import sqlalchemy as sa
from alembic import op

revision = "0106_review_rating"
down_revision = "0105_photo_upload_group"
branch_labels = None
depends_on = None

# What an existing review without a number is worth. Neutral on a scale of one
# to five, so the backfill does not invent praise or complaint.
DEFAULT_RATING = 3


def upgrade():
    op.add_column("reviews", sa.Column("rating", sa.SmallInteger(), nullable=True))
    op.execute(sa.text(f"UPDATE reviews SET rating = {DEFAULT_RATING} WHERE rating IS NULL"))
    op.alter_column("reviews", "rating", nullable=False)
    op.create_check_constraint("ck_reviews_rating_range", "reviews", "rating BETWEEN 1 AND 5")


def downgrade():
    op.drop_constraint("ck_reviews_rating_range", "reviews", type_="check")
    op.drop_column("reviews", "rating")
