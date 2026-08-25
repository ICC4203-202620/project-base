import sqlalchemy as sa
from alembic import op

revision = "0005_create_follows"
down_revision = "0004_create_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_follows",
        sa.Column("follower_id", sa.Uuid(), nullable=False),
        sa.Column("followed_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("follower_id", "followed_id"),
        sa.CheckConstraint("follower_id <> followed_id", name="ck_user_follows_not_self"),
    )
    op.create_index("ix_user_follows_followed_id", "user_follows", ["followed_id"])
    op.create_table(
        "restaurant_follows",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "restaurant_id"),
    )
    op.create_index("ix_restaurant_follows_restaurant_id", "restaurant_follows", ["restaurant_id"])


def downgrade():
    op.drop_index("ix_restaurant_follows_restaurant_id", table_name="restaurant_follows")
    op.drop_table("restaurant_follows")
    op.drop_index("ix_user_follows_followed_id", table_name="user_follows")
    op.drop_table("user_follows")
