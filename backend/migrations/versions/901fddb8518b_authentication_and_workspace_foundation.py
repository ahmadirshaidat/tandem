"""Authentication and workspace foundation

Revision ID: 901fddb8518b
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "901fddb8518b"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'editor', 'viewer')", name="ck_invitation_role"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_invitation_workspace_email", "invitations", ["workspace_id", "email"], unique=False
    )
    op.create_index(
        op.f("ix_invitations_workspace_id"), "invitations", ["workspace_id"], unique=False
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('owner', 'admin', 'editor', 'viewer')", name="ck_member_role"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_memberships_workspace_id"), "memberships", ["workspace_id"], unique=False
    )
    op.create_table(
        "password_resets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_password_resets_user_id"), "password_resets", ["user_id"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_sessions_family_id"), "sessions", ["family_id"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_family_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_password_resets_user_id"), table_name="password_resets")
    op.drop_table("password_resets")
    op.drop_index(op.f("ix_memberships_workspace_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_index(op.f("ix_invitations_workspace_id"), table_name="invitations")
    op.drop_index("ix_invitation_workspace_email", table_name="invitations")
    op.drop_table("invitations")
    op.drop_table("workspaces")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    # ### end Alembic commands ###
