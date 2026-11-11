"""WhatsApp e contato do fornecedor (envio da ordem de compra)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-11 00:10:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fornecedor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('contato', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('whatsapp', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('fornecedor', schema=None) as batch_op:
        batch_op.drop_column('whatsapp')
        batch_op.drop_column('contato')
