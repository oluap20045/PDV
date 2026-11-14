/* Loja online: carrinho no aparelho (localStorage), pedido por POST /loja/pedido */
(function () {
    'use strict';
    const produtos = {};
    JSON.parse(document.getElementById('dados-produtos').textContent).forEach(p => { produtos[p.id] = p; });
    const elCombos = document.getElementById('dados-combos');
    const COMBOS = elCombos ? JSON.parse(elCombos.textContent) : [];

    const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* aba anônima */ } };
    const ler = (k, padrao) => { try { return JSON.parse(localStorage.getItem(k)) || padrao; } catch (e) { return padrao; } };
    const reais = v => v.toFixed(2).replace('.', ',');
    const $ = s => document.querySelector(s);
    const rastro = (...a) => { if (window.lojaRastro) window.lojaRastro(...a); };   // analisador de tráfego (rastreio.js)

    // carrinho salvo: descarta o que sumiu da vitrine e respeita o estoque de agora
    let carrinho = {};
    Object.entries(ler('loja-carrinho', {})).forEach(([id, q]) => {
        if (produtos[id]) carrinho[id] = Math.min(q, produtos[id].max);
    });

    function definir(id, q) {
        q = Math.max(0, Math.min(q, produtos[id] ? produtos[id].max : 0));
        if (q) carrinho[id] = q; else delete carrinho[id];
        guardar('loja-carrinho', carrinho);
        desenhar();
    }

    function controle(id) {
        const q = carrinho[id] || 0;
        const el = document.querySelector(`[data-controle="${id}"]`);
        if (!el) return;
        if (!q) {
            el.innerHTML = '<button type="button" class="adicionar">Adicionar</button>';
        } else {
            const cheio = q >= produtos[id].max;
            el.innerHTML = `<button type="button" class="menos" aria-label="Tirar um">−</button>
                <span class="num" aria-live="polite">${q}</span>
                <button type="button" class="mais" aria-label="Mais um" ${cheio ? 'disabled' : ''}>+</button>`;
        }
    }

    // ---------- modo "montando combo": só os sabores do combo + barra de progresso
    let comboAtivo = null;
    const reaisCurto = v => (Math.round(v * 100) % 100 === 0 ? String(Math.round(v)) : reais(v));

    function montarCombo(id) {
        const c = COMBOS.find(x => String(x.id) === String(id));
        if (!c) return;
        rastro('clique', 'Montar combo: ' + c.nome);
        comboAtivo = c;
        document.querySelectorAll('.chip').forEach(x => x.classList.remove('ativo'));
        document.querySelectorAll('.produto').forEach(p => { p.hidden = !p.dataset.combos.split(' ').includes(String(c.id)); });
        desenhar();
        const barra = $('#modo-combo');
        barra.scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    function sairDoCombo() {
        comboAtivo = null;
        document.querySelectorAll('.chip').forEach(x => x.classList.toggle('ativo', !x.dataset.cat));
        document.querySelectorAll('.produto').forEach(p => { p.hidden = false; });
        desenhar();
    }

    // progresso de cada combo: quantos combos fechados + quantos sabores já escolhidos para o próximo
    function progresso(c, r) {
        const fechados = r.grupos.filter(g => g.combo.id === c.id).length;
        const parcial = c.produtos.reduce((s, id) => s + (r.resto[id] || 0), 0) % c.quantidade;
        return {fechados, parcial};
    }

    function textoProgresso(c, p) {
        if (c.promocao) return p.fechados ? `✓ ${p.fechados > 1 ? p.fechados + ' unidades' : 'No carrinho'} com desconto` : 'Preço promocional';
        if (p.parcial) {
            const falta = c.quantidade - p.parcial;
            return `${p.parcial} de ${c.quantidade} escolhido${p.parcial > 1 ? 's' : ''} · falta${falta > 1 ? 'm' : ''} ${falta}`
                + (p.fechados ? ` (${p.fechados} combo${p.fechados > 1 ? 's' : ''} pronto${p.fechados > 1 ? 's' : ''})` : '');
        }
        if (p.fechados) return `✓ ${p.fechados > 1 ? p.fechados + ' combos prontos' : 'Combo pronto'} no carrinho`;
        return `Escolha ${c.quantidade} sabores`;
    }

    function desenharPromos(r) {
        COMBOS.forEach(c => {
            const card = document.querySelector(`.promo[data-combo="${c.id}"]`);
            if (!card) return;
            const p = progresso(c, r);
            const box = card.querySelector('.promo-progresso');
            const ativo = p.fechados || p.parcial;
            box.hidden = !ativo;
            card.classList.toggle('pronto', !!p.fechados && !p.parcial);
            card.classList.toggle('ativo', comboAtivo && comboAtivo.id === c.id);
            if (ativo) {
                box.querySelector('.progresso span').style.width = `${p.parcial ? p.parcial / c.quantidade * 100 : 100}%`;
                box.querySelector('small').textContent = textoProgresso(c, p);
            }
            card.querySelector('.promo-botao').textContent = c.promocao ? (p.fechados ? '✓ No carrinho' : 'Ver oferta')
                : (p.fechados && !p.parcial ? 'Montar outro' : (p.parcial ? 'Continuar' : 'Montar combo'));
        });
        const barra = $('#modo-combo');
        if (!barra) return;
        barra.hidden = !comboAtivo;
        if (comboAtivo) {
            const c = comboAtivo, p = progresso(c, r);
            $('#modo-combo-titulo').textContent = c.rotulo || c.nome;
            $('#modo-combo-status').textContent = `${oferta(c)} · ${textoProgresso(c, p)}`;
            $('#modo-combo-barra').style.width = `${p.parcial ? p.parcial / c.quantidade * 100 : (p.fechados ? 100 : 0)}%`;
            barra.classList.toggle('pronto', !!p.fechados && !p.parcial);
        }
    }

    const oferta = c => (c.promocao ? `por R$ ${reaisCurto(c.preco)}` : `${c.quantidade} por R$ ${reaisCurto(c.preco)}`);

    // combos "leve N por R$ X" (mesma regra do servidor: static/js/combos.js)
    function combos() {
        const itens = Object.keys(carrinho).map(id => ({id: +id, qtd: carrinho[id], preco: produtos[id].preco}));
        return window.Combos ? Combos.aplicar(itens, COMBOS) : {grupos: [], resto: {}};
    }

    function desenharCombos(r) {
        const box = $('#carrinho-combos');
        box.innerHTML = '';
        r.grupos.forEach(g => {
            const qtdPorId = {};
            g.linhas.forEach(l => { qtdPorId[l.id] = (qtdPorId[l.id] || 0) + l.qtd; });
            const d = document.createElement('div');
            d.className = 'combo-linha';
            d.innerHTML = '<div><strong></strong><small></small></div><span class="economia"></span>';
            d.querySelector('strong').textContent = `${g.combo.promocao ? '🏷️ Promoção:' : '🎁'} ${g.combo.rotulo || g.combo.nome} · ${oferta(g.combo)}`;
            d.querySelector('small').textContent = Object.entries(qtdPorId).map(([id, q]) => `${q}× ${produtos[id].nome}`).join(', ');
            d.querySelector('.economia').textContent = `− R$ ${reais(g.economia)}`;
            box.appendChild(d);
        });
        (window.Combos ? Combos.faltando(r.resto, COMBOS) : []).forEach(f => {
            const d = document.createElement('p');
            d.className = 'combo-falta';
            d.textContent = `Falta${f.falta > 1 ? 'm' : ''} ${f.falta} para fechar o combo ${f.combo.rotulo || f.combo.nome} (${f.combo.quantidade} por R$ ${reaisCurto(f.combo.preco)})`;
            box.appendChild(d);
        });
    }

    function desenhar() {
        Object.keys(produtos).forEach(controle);
        const ids = Object.keys(carrinho);
        const qtd = ids.reduce((s, id) => s + carrinho[id], 0);
        const r = combos();
        desenharCombos(r);
        desenharPromos(r);
        const total = ids.reduce((s, id) => s + carrinho[id] * produtos[id].preco, 0)
            - r.grupos.reduce((s, g) => s + g.economia, 0);
        $('#barra').hidden = !qtd;
        $('#barra-qtd').textContent = qtd;
        $('#barra-total').textContent = reais(total);
        $('#topo-qtd').hidden = !qtd;
        $('#topo-qtd').textContent = qtd;
        $('#carrinho-total').textContent = reais(total);
        $('#carrinho-itens').innerHTML = ids.length ? ids.map(id => {
            const p = produtos[id];
            return `<div class="linha" data-id="${id}">
                <div><div class="linha-nome"></div><div class="linha-preco">${carrinho[id]} × R$ ${reais(p.preco)}</div></div>
                <div class="qtd" data-linha="${id}">
                    <button type="button" class="menos" aria-label="Tirar um">−</button>
                    <span class="num">${carrinho[id]}</span>
                    <button type="button" class="mais" aria-label="Mais um" ${carrinho[id] >= p.max ? 'disabled' : ''}>+</button>
                </div></div>`;
        }).join('') : '<p class="carrinho-vazio">Carrinho vazio.</p>';
        // nome via textContent (nunca HTML vindo do cadastro)
        document.querySelectorAll('#carrinho-itens .linha').forEach(l => {
            l.querySelector('.linha-nome').textContent = produtos[l.dataset.id].nome;
        });
        $('#enviar').disabled = !ids.length;
    }

    document.addEventListener('click', ev => {
        const b = ev.target.closest('button');
        if (!b) return;
        const caixa = b.closest('[data-controle], [data-linha]');
        if (caixa) {
            const id = caixa.dataset.controle || caixa.dataset.linha;
            if (b.classList.contains('adicionar')) rastro('adicionar', produtos[id] && produtos[id].nome, id);
            if (b.classList.contains('adicionar') || b.classList.contains('mais')) definir(id, (carrinho[id] || 0) + 1);
            if (b.classList.contains('menos')) definir(id, (carrinho[id] || 0) - 1);
        }
        if (b.classList.contains('chip')) {
            rastro('categoria', b.dataset.cat || 'Tudo');
            comboAtivo = null;
            document.querySelectorAll('.chip').forEach(c => c.classList.toggle('ativo', c === b));
            document.querySelectorAll('.produto').forEach(p => { p.hidden = !!b.dataset.cat && p.dataset.cat !== b.dataset.cat; });
            desenhar();
        }
        if (b.classList.contains('promo-botao')) montarCombo(b.dataset.combo);
        if (b.id === 'modo-combo-sair') sairDoCombo();
    });

    const dialogo = $('#carrinho');
    const abrir = () => { $('#erro').hidden = true; rastro('carrinho'); dialogo.showModal(); };
    $('#barra').addEventListener('click', abrir);
    $('#abrir-carrinho').addEventListener('click', abrir);
    dialogo.addEventListener('click', ev => { if (ev.target === dialogo) dialogo.close(); });   // toque fora fecha

    // dados do cliente lembrados neste aparelho
    const form = $('#form-pedido');
    const cliente = ler('loja-cliente', {});
    ['nome', 'whatsapp', 'entrega'].forEach(c => { if (cliente[c]) form.elements[c].value = cliente[c]; });
    if (cliente.pagamento) {
        const r = form.querySelector(`input[name="pagamento"][value="${CSS.escape(cliente.pagamento)}"]`);
        if (r) r.checked = true;
    }

    function erro(msg) { const e = $('#erro'); e.textContent = msg; e.hidden = false; e.scrollIntoView({block: 'nearest'}); }

    form.addEventListener('submit', async ev => {
        ev.preventDefault();
        const f = form.elements;
        const dados = {
            nome: f.nome.value.trim(), whatsapp: f.whatsapp.value.trim(), entrega: f.entrega.value.trim(),
            pagamento: (form.querySelector('input[name="pagamento"]:checked') || {}).value || '',
            observacao: f.observacao.value.trim(), site: f.site.value,
            itens: Object.entries(carrinho).map(([id, qtd]) => ({id: +id, qtd})),
        };
        if (dados.nome.length < 2) return erro('Informe seu nome.');
        if (!/^\d{10,11}$/.test(dados.whatsapp.replace(/\D/g, '').replace(/^55(?=\d{10,11}$)/, ''))) return erro('Informe o WhatsApp com DDD.');
        if (!dados.entrega) return erro('Informe o bloco e o apartamento.');
        guardar('loja-cliente', {nome: dados.nome, whatsapp: dados.whatsapp, entrega: dados.entrega, pagamento: dados.pagamento});

        const botao = $('#enviar');
        botao.disabled = true;
        botao.textContent = 'Enviando…';
        try {
            const r = await fetch(form.dataset.acao || 'pedido', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(dados),
            });
            const resp = await r.json().catch(() => ({}));
            if (r.ok && resp.url) {
                const total = Object.entries(carrinho).reduce((s, [id, q]) => s + q * produtos[id].preco, 0)
                    - combos().grupos.reduce((s, g) => s + g.economia, 0);
                rastro('pedido', 'R$ ' + reais(total));
                guardar('loja-carrinho', {});
                window.location.href = resp.url;
                return;
            }
            if (resp.faltou) {           // estoque mudou: ajusta o carrinho ao que tem
                resp.faltou.forEach(x => {
                    if (produtos[x.id]) { produtos[x.id].max = x.disponivel; definir(x.id, Math.min(carrinho[x.id] || 0, x.disponivel)); }
                });
            }
            erro(resp.erro || 'Não deu para enviar. Tente de novo.');
        } catch (e) {
            erro('Sem conexão. Confira a internet e tente de novo.');
        } finally {
            botao.disabled = !Object.keys(carrinho).length;
            botao.textContent = 'Fazer pedido';
        }
    });

    desenhar();
})();
