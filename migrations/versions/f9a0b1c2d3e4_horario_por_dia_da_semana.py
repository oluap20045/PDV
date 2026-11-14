"""Loja online: horário por dia da semana (loja_semana) no lugar de abre/fecha/dias únicos e do texto de entrega

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-11-13 22:30:00

"""
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9a0b1c2d3e4'
down_revision = 'e8f9a0b1c2d3'
branch_labels = None
depends_on = None

PADRAO = json.dumps([['18:00', '23:00']] * 7)


def _hhmm(t):
    """time / timedelta (MariaDB) / '9:00:00' -> '09:00'."""
    if hasattr(t, 'total_seconds'):
        m = int(t.total_seconds()) // 60
        return f'{m // 60 % 24:02d}:{m % 60:02d}'
    h, m = str(t).split(':')[:2]
    return f'{int(h):02d}:{int(m):02d}'


def upgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('loja_semana', sa.String(length=200), nullable=False, server_default=PADRAO))
    con = op.get_bind()
    for id_, abre, fecha, dias in con.execute(sa.text('SELECT id, loja_abre, loja_fecha, loja_dias FROM empresa')).fetchall():
        a, f = _hhmm(abre), _hhmm(fecha)
        semana = [[a, f] if str(i) in (dias or '') else None for i in range(7)]
        con.execute(sa.text('UPDATE empresa SET loja_semana = :s WHERE id = :i'), {'s': json.dumps(semana), 'i': id_})
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        for c in ('loja_abre', 'loja_fecha', 'loja_dias', 'loja_horario'):
            batch_op.drop_column(c)


def downgrade():
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.add_column(sa.Column('loja_abre', sa.Time(), nullable=False, server_default='18:00:00'))
        batch_op.add_column(sa.Column('loja_fecha', sa.Time(), nullable=False, server_default='23:00:00'))
        batch_op.add_column(sa.Column('loja_dias', sa.String(length=7), nullable=False, server_default='0123456'))
        batch_op.add_column(sa.Column('loja_horario', sa.String(length=60), nullable=True))
    con = op.get_bind()
    for id_, semana in con.execute(sa.text('SELECT id, loja_semana FROM empresa')).fetchall():
        grade = json.loads(semana or '[]')
        abertos = [i for i, j in enumerate(grade) if j]
        a, f = (grade[abertos[0]] if abertos else ['18:00', '23:00'])
        con.execute(sa.text('UPDATE empresa SET loja_abre = :a, loja_fecha = :f, loja_dias = :d, loja_horario = :h WHERE id = :i'),
                    {'a': a + ':00', 'f': f + ':00', 'd': ''.join(map(str, abertos)) or '0123456', 'h': f'{a} às {f}', 'i': id_})
    with op.batch_alter_table('empresa', schema=None) as batch_op:
        batch_op.drop_column('loja_semana')
