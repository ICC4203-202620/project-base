"""Relate the photographs published in one act.

Each photograph travels in its own request, so the interface can show the
progress of every file and retry only the one that failed. The group is what
keeps that set a single act: the photographs that share it are one entry in
the feed and, later, one notification.
"""

import sqlalchemy as sa
from alembic import op

revision = "0105_photo_upload_group"
down_revision = "0104_photo_dish_and_caption"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("photos", sa.Column("upload_group", sa.Uuid(), nullable=True))
    # The activity item of a group resolves through this index rather than by
    # walking the table.
    op.create_index("ix_photos_upload_group", "photos", ["upload_group"])


def downgrade():
    op.drop_index("ix_photos_upload_group", table_name="photos")
    op.drop_column("photos", "upload_group")
