"""Adiciona cadastro de clientes

Revision ID: d8e2b4c6a1f3
Revises: c3a1f0d2b7e4
Create Date: 2026-11-07 19:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8e2b4c6a1f3'
down_revision = 'c3a1f0d2b7e4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cliente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=150), nullable=False),
        sa.Column('telefone', sa.String(length=20), nullable=True),
        sa.Column('whatsapp', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=150), nullable=True),
        sa.Column('cpf', sa.String(length=11), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cliente_cpf'), ['cpf'], unique=True)


def downgrade():
    with op.batch_alter_table('cliente', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cliente_cpf'))
    op.drop_table('cliente')
