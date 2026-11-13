"""Login, criação de conta, troca de senha e lista de usuários."""
import re
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from app import db
from app.models import Empresa, Usuario

bp = Blueprint('auth', __name__)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Entre com seu usuário e senha para continuar.'
login_manager.login_message_category = 'warning'

SENHA_MINIMA = 6
RE_LOGIN = re.compile(r'^[a-z0-9._-]{3,50}$')
# o que pode ser acessado sem estar logado
LIVRES = {'auth.login', 'auth.cadastro', 'static'}


@login_manager.user_loader
def carregar_usuario(ident):
    uid, _, carimbo = (ident or '').partition(':')
    if not uid.isdigit():
        return None
    u = db.session.get(Usuario, int(uid))
    if u is None or not u.ativo or u.carimbo_senha() != carimbo:
        return None
    return u


@login_manager.unauthorized_handler
def nao_autorizado():
    if request.accept_mimetypes.best == 'application/json' or request.is_json:
        return jsonify(erro='Sessão expirada. Entre de novo.'), 401
    flash(login_manager.login_message, login_manager.login_message_category)
    destino = request.full_path if request.method == 'GET' else None
    return redirect(url_for('auth.login', next=destino.rstrip('?') if destino else None))


def exigir_login():
    """before_request da aplicação: tudo exige login, menos as rotas LIVRES e a loja online.

    No endereço público da loja (LOJA_HOST, o que chega pela internet) só existe a loja: o resto dá 404,
    mesmo para quem tem login — o sistema interno continua só na rede de casa / ZeroTier."""
    publico = request.blueprint == 'loja' or request.endpoint == 'static'
    if request.host.split(':')[0].lower() in current_app.config.get('LOJA_HOST', set()):
        if request.path in ('/', ''):
            return redirect('/loja/')
        return None if publico else abort(404)
    if publico or request.endpoint in LIVRES or current_user.is_authenticated:
        return None
    return login_manager.unauthorized()


def _destino_seguro(alvo):
    # só caminhos internos ("/venda"), nunca "//site" ou "https://site"
    if alvo and alvo.startswith('/') and not alvo.startswith('//') and '\\' not in alvo:
        return alvo
    return url_for('main.index')


def _cadastro_liberado():
    return Usuario.query.count() == 0 or Empresa.atual().cadastro_aberto


def _validar_senha(senha, confirmacao):
    if len(senha) < SENHA_MINIMA:
        return f'A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.'
    if senha != confirmacao:
        return 'A confirmação não bate com a senha.'
    return None


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(_destino_seguro(request.args.get('next')))
    if Usuario.query.count() == 0:
        flash('Nenhum usuário ainda: crie o primeiro acesso.', 'info')
        return redirect(url_for('auth.cadastro'))

    if request.method == 'POST':
        login_txt = (request.form.get('login') or '').strip().lower()
        senha = request.form.get('senha') or ''
        u = Usuario.query.filter_by(login=login_txt).first()
        agora = datetime.now()
        if u and u.bloqueado(agora):
            minutos = max(1, int((u.bloqueado_ate - agora).total_seconds() // 60) + 1)
            flash(f'Muitas tentativas erradas. Tente de novo em {minutos} min.', 'danger')
        elif u and u.ativo and u.senha_confere(senha):
            u.tentativas_falhas = 0
            u.bloqueado_ate = None
            u.ultimo_acesso = agora
            db.session.commit()
            login_user(u, remember=request.form.get('lembrar') == '1')
            return redirect(_destino_seguro(request.args.get('next')))
        else:
            if u and u.ativo:
                u.tentativas_falhas = (u.tentativas_falhas or 0) + 1
                if u.tentativas_falhas >= Usuario.MAX_TENTATIVAS:
                    u.bloqueado_ate = agora + Usuario.BLOQUEIO
                    u.tentativas_falhas = 0
                db.session.commit()
            # mesma mensagem para usuário inexistente, desativado ou senha errada
            flash('Usuário ou senha incorretos.', 'danger')
        return render_template('login.html', login=login_txt, cadastro=_cadastro_liberado()), 401

    return render_template('login.html', login='', cadastro=_cadastro_liberado())


@bp.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    """Criar conta pela tela de login (pode ser fechado em Empresa). O primeiro usuário sempre pode."""
    if not _cadastro_liberado() and not current_user.is_authenticated:
        flash('A criação de contas está fechada. Peça a um usuário já cadastrado.', 'warning')
        return redirect(url_for('auth.login'))
    primeiro = Usuario.query.count() == 0
    dados = {'nome': '', 'login': ''}

    if request.method == 'POST':
        dados['nome'] = (request.form.get('nome') or '').strip()[:100]
        dados['login'] = (request.form.get('login') or '').strip().lower()
        senha = request.form.get('senha') or ''
        erro = None
        if not dados['nome']:
            erro = 'Informe seu nome.'
        elif not RE_LOGIN.match(dados['login']):
            erro = 'Usuário: 3 a 50 caracteres, só letras minúsculas, números, ponto, hífen ou _.'
        elif Usuario.query.filter_by(login=dados['login']).first():
            erro = 'Esse usuário já existe. Escolha outro.'
        else:
            erro = _validar_senha(senha, request.form.get('confirmacao') or '')
        if erro:
            flash(erro, 'danger')
        else:
            u = Usuario(nome=dados['nome'], login=dados['login'], ativo=True)
            u.definir_senha(senha)
            db.session.add(u)
            db.session.commit()
            if current_user.is_authenticated:      # criado por quem já está logado (tela de usuários)
                flash(f'Usuário "{u.login}" criado.', 'success')
                return redirect(url_for('auth.usuarios'))
            u.ultimo_acesso = datetime.now()
            db.session.commit()
            login_user(u, remember=True)
            flash(f'Bem-vindo(a), {u.nome.split()[0]}! Conta criada.', 'success')
            return redirect(url_for('main.index'))

    return render_template('cadastro.html', dados=dados, primeiro=primeiro, senha_minima=SENHA_MINIMA)


@bp.route('/logout', methods=['POST'])
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/conta/senha', methods=['GET', 'POST'])
@login_required
def trocar_senha():
    if request.method == 'POST':
        atual = request.form.get('atual') or ''
        nova = request.form.get('nova') or ''
        erro = None
        if not current_user.senha_confere(atual):
            erro = 'Senha atual incorreta.'
        elif nova == atual:
            erro = 'A nova senha precisa ser diferente da atual.'
        else:
            erro = _validar_senha(nova, request.form.get('confirmacao') or '')
        if erro:
            flash(erro, 'danger')
        else:
            current_user.definir_senha(nova)
            db.session.commit()
            # o carimbo da senha mudou: renova a sessão deste aparelho; os outros caem
            login_user(current_user, remember=True)
            flash('Senha alterada. Outros aparelhos conectados vão pedir login de novo.', 'success')
            return redirect(url_for('main.index'))
    return render_template('trocar_senha.html', senha_minima=SENHA_MINIMA)


@bp.route('/usuarios')
@login_required
def usuarios():
    return render_template('usuarios.html', usuarios=Usuario.query.order_by(Usuario.nome).all(),
                           empresa=Empresa.atual())


@bp.route('/usuario/<int:id>/ativo', methods=['POST'])
@login_required
def alternar_ativo(id):
    u = db.session.get(Usuario, id)
    if u is None:
        flash('Usuário não encontrado.', 'danger')
    elif u.id == current_user.id:
        flash('Você não pode desativar o próprio acesso.', 'warning')
    else:
        u.ativo = not u.ativo
        u.tentativas_falhas, u.bloqueado_ate = 0, None
        db.session.commit()
        flash(f'Usuário "{u.login}" {"reativado" if u.ativo else "desativado (não entra mais)"}.', 'success')
    return redirect(url_for('auth.usuarios'))


@bp.route('/usuarios/cadastro-aberto', methods=['POST'])
@login_required
def alternar_cadastro():
    empresa = Empresa.atual()
    empresa.cadastro_aberto = request.form.get('aberto') == '1'
    db.session.commit()
    flash('Criar conta na tela de login: ' + ('liberado.' if empresa.cadastro_aberto else 'fechado.'), 'success')
    return redirect(url_for('auth.usuarios'))
