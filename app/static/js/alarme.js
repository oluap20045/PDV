/* Alarme de pedido da loja online, em todas as telas do PDV.
   A cada 15 s pergunta ao servidor se chegou pedido novo. Se chegou: aviso grande na tela, som a cada 20 s
   e notificação do navegador, até alguém clicar em "Vi o pedido" (vale para todas as abas deste aparelho).
   O sininho no menu liga/desliga o som neste aparelho. */
(function () {
    'use strict';
    const url = document.body.dataset.alarmeUrl;
    if (!url) return;

    const ler = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
    const gravar = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* aba anônima */ } };
    const somLigado = () => ler('alarme-som') !== '0';

    const aviso = document.getElementById('alarme-aviso');
    const sino = document.getElementById('alarme-sino');
    const selo = document.getElementById('selo-pedidos-loja');
    const tituloOriginal = document.title;
    let pendentes = [], ultimo = 0, timerSom = null, timerTitulo = null, falhas = 0;

    // ---------------------------------------------------------------- som (Web Audio: sem arquivo para baixar)
    let ctx = null;
    function audio() {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
        }
        if (ctx.state === 'suspended') ctx.resume().catch(() => {});
        return ctx;
    }
    // o navegador só libera som depois de um clique/tecla na página: destrava no primeiro gesto
    ['pointerdown', 'keydown'].forEach(ev => document.addEventListener(ev, () => { audio(); atualizarAvisoSom(); }, {once: false, passive: true}));

    function tocar() {
        if (!somLigado()) return;
        const a = audio();
        if (!a || a.state !== 'running') { atualizarAvisoSom(); return; }
        // "plim-plom" duas vezes
        [[0, 988], [0.22, 784], [0.7, 988], [0.92, 784]].forEach(([t, f]) => {
            const o = a.createOscillator(), g = a.createGain(), inicio = a.currentTime + t;
            o.type = 'sine'; o.frequency.value = f;
            g.gain.setValueAtTime(0.0001, inicio);
            g.gain.exponentialRampToValueAtTime(0.5, inicio + 0.02);
            g.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.5);
            o.connect(g).connect(a.destination);
            o.start(inicio); o.stop(inicio + 0.55);
        });
    }

    function atualizarAvisoSom() {
        const el = document.getElementById('alarme-sem-som');
        if (el) el.hidden = !(somLigado() && pendentes.length && (!ctx || ctx.state !== 'running'));
    }

    function atualizarSino() {
        if (!sino) return;
        sino.textContent = somLigado() ? '🔔' : '🔕';
        sino.title = somLigado() ? 'Alarme de pedido da loja: ligado (clique para silenciar)' : 'Alarme de pedido da loja: sem som (clique para ligar)';
        sino.setAttribute('aria-pressed', somLigado() ? 'true' : 'false');
    }

    // ---------------------------------------------------------------- aviso na tela
    const brl = v => 'R$\u00a0' + v.toFixed(2).replace('.', ',');
    function mostrar() {
        if (!aviso) return;
        const lista = aviso.querySelector('[data-alarme-lista]');
        lista.textContent = '';
        pendentes.forEach(p => {
            const li = document.createElement('li');
            li.textContent = `${p.hora} · ${p.cliente}` + (p.entrega ? ` · ${p.entrega}` : '') +
                ` · ${p.itens} ${p.itens === 1 ? 'item' : 'itens'} · ${brl(p.total)}`;
            lista.appendChild(li);
        });
        aviso.querySelector('[data-alarme-titulo]').textContent =
            pendentes.length === 1 ? 'Novo pedido na loja!' : `${pendentes.length} pedidos novos na loja!`;
        aviso.hidden = false;
        atualizarAvisoSom();
        if (!timerSom) { tocar(); timerSom = setInterval(tocar, 20000); }
        if (!timerTitulo) {
            let n = 0;
            timerTitulo = setInterval(() => { document.title = (n++ % 2) ? tituloOriginal : '🔔 Novo pedido!'; }, 1000);
        }
    }

    function esconder() {
        if (aviso) aviso.hidden = true;
        clearInterval(timerSom); clearInterval(timerTitulo);
        timerSom = timerTitulo = null;
        document.title = tituloOriginal;
    }

    function confirmar() {
        gravar('alarme-visto', String(ultimo));
        pendentes = [];
        esconder();
        if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
    }

    function notificar(novos) {
        if (!('Notification' in window) || Notification.permission !== 'granted') return;
        try {
            const p = novos[novos.length - 1];
            const n = new Notification(novos.length === 1 ? '🛒 Novo pedido na loja' : `🛒 ${novos.length} pedidos novos na loja`, {
                body: `${p.cliente}${p.entrega ? ' · ' + p.entrega : ''} · ${brl(p.total)}`, tag: 'pedido-loja', renotify: true,
            });
            n.onclick = () => { window.focus(); n.close(); };
        } catch (e) { /* alguns navegadores só notificam por service worker */ }
    }

    // ---------------------------------------------------------------- consulta ao servidor
    async function consultar() {
        let visto = ler('alarme-visto');
        try {
            const r = await fetch(url + (visto !== null ? '?desde=' + encodeURIComponent(visto) : ''),
                                  {headers: {Accept: 'application/json'}, cache: 'no-store', credentials: 'same-origin'});
            if (r.redirected || !r.ok) throw new Error('sem login');
            const d = await r.json();
            falhas = 0;
            ultimo = d.ultimo;
            if (selo) { selo.textContent = '🛒 ' + d.abertos; selo.hidden = !d.abertos; }
            if (visto === null) { gravar('alarme-visto', String(d.ultimo)); return; }   // 1ª vez neste aparelho: não toca o que já existia
            const novos = d.novos.filter(p => !pendentes.some(x => x.id === p.id));
            pendentes = d.novos;
            if (!pendentes.length) {                       // cancelados / já vistos em outra aba
                if (d.ultimo > +visto) gravar('alarme-visto', String(d.ultimo));
                esconder();
                return;
            }
            if (novos.length) notificar(novos);
            mostrar();
        } catch (e) {
            falhas++;
        }
    }

    // outra aba clicou em "Vi o pedido"
    window.addEventListener('storage', ev => {
        if (ev.key === 'alarme-visto' && ev.newValue !== null && +ev.newValue >= ultimo) { pendentes = []; esconder(); }
        if (ev.key === 'alarme-som') { atualizarSino(); if (!somLigado()) { clearInterval(timerSom); timerSom = null; } }
    });

    if (aviso) {
        aviso.querySelector('[data-alarme-ok]').addEventListener('click', confirmar);
        aviso.querySelector('[data-alarme-ver]').addEventListener('click', confirmar);
    }
    if (sino) {
        sino.addEventListener('click', ev => {
            ev.preventDefault();
            gravar('alarme-som', somLigado() ? '0' : '1');
            atualizarSino();
            if (somLigado()) {
                tocar();                                   // teste: já ouve como vai tocar
                if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
                if (pendentes.length && !timerSom) timerSom = setInterval(tocar, 20000);
            } else {
                clearInterval(timerSom); timerSom = null;
            }
        });
    }
    atualizarSino();

    // abriu a tela de Pedidos: já está vendo, não precisa tocar pelo que existia até agora
    const naTelaDePedidos = location.pathname === '/pedidos';
    consultar().then(() => { if (naTelaDePedidos && pendentes.length) confirmar(); });
    // não pausa com a aba escondida: o alarme serve justamente para quem está em outra tela
    // (o navegador pode espaçar para 1x/min em aba no fundo; continua tocando)
    setInterval(() => { if (falhas < 20) consultar(); }, 15000);
})();
