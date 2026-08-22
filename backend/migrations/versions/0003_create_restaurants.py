import sqlalchemy as sa
from alembic import op

revision = "0003_create_restaurants"
down_revision = "0002_create_auth_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cuisine_styles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
    )
    op.create_index("uq_cuisine_styles_slug", "cuisine_styles", ["slug"], unique=True)

    op.create_table(
        "restaurants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("normalized_name", sa.String(240), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("normalized_address", sa.String(510), nullable=False),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("latitude", sa.Numeric(8, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "uq_restaurants_identity_key",
        "restaurants",
        ["identity_key"],
        unique=True,
    )
    op.create_index(
        "ix_restaurants_normalized_name_id",
        "restaurants",
        ["normalized_name", "id"],
    )

    op.create_table(
        "restaurant_cuisine_styles",
        sa.Column("restaurant_id", sa.Uuid(), primary_key=True),
        sa.Column("cuisine_style_id", sa.Uuid(), primary_key=True),
    )
    op.create_index(
        "ix_restaurant_cuisine_styles_cuisine_style_id",
        "restaurant_cuisine_styles",
        ["cuisine_style_id"],
    )


def downgrade():
    op.drop_index(
        "ix_restaurant_cuisine_styles_cuisine_style_id",
        table_name="restaurant_cuisine_styles",
    )
    op.drop_table("restaurant_cuisine_styles")
    op.drop_index("ix_restaurants_normalized_name_id", table_name="restaurants")
    op.drop_index("uq_restaurants_identity_key", table_name="restaurants")
    op.drop_table("restaurants")
    op.drop_index("uq_cuisine_styles_slug", table_name="cuisine_styles")
    op.drop_table("cuisine_styles")
