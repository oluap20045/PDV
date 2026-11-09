"""Usuarios e login (multiusuario)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-11-09 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'usuario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=100), nullable=False),
        sa.Column('login', sa.String(length=50), nullable=False),
        sa.Column('senha_hash', sa.String(length=255), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('ultimo_acesso', sa.DateTime(), nullable=True),
        sa.Column('tentativas_falhas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bloqueado_ate', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('login', name='uq_usuario_login'),
    )
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.add_column(sa.Column('usuario_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_venda_usuario_id', ['usuario_id'])
        batch_op.create_foreign_key('fk_venda_usuario', 'usuario', ['usuario_id'], ['id'])
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cadastro_aberto', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('cadastro_aberto')
    with op.batch_alter_table('venda', schema=None) as batch_op:
        batch_op.drop_constraint('fk_venda_usuario', type_='foreignkey')
        batch_op.drop_index('ix_venda_usuario_id')
        batch_op.drop_column('usuario_id')
    op.drop_table('usuario')
