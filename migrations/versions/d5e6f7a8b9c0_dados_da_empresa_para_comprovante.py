"""Dados da empresa para o comprovante de venda

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-07 23:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'empresa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=120), nullable=False),
        sa.Column('cnpj', sa.String(length=14), nullable=True),
        sa.Column('telefone', sa.String(length=20), nullable=True),
        sa.Column('endereco', sa.String(length=200), nullable=True),
        sa.Column('mensagem', sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('empresa')
