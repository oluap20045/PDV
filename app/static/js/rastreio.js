/* Analisador de tráfego da loja: conta acessos e cliques, sem cookie de terceiros e sem dado pessoal.
   O "visitante" é um código aleatório guardado no próprio aparelho (localStorage).
   ?o=folder (ou whatsapp, instagram...) no link marca de onde a pessoa veio.
   ?nao_contar=1 desliga a contagem neste aparelho (use no seu celular); ?contar=1 liga de novo. */
(function () {
    'use strict';
    const url = document.body.dataset.rastroUrl;
    if (!url) return;

    const ler = (s, k) => { try { return s.getItem(k); } catch (e) { return null; } };
    const gravar = (s, k, v) => { try { s.setItem(k, v); } catch (e) { /* aba anônima / bloqueado */ } };
    const params = new URLSearchParams(location.search);

    if (params.get('nao_contar') === '1') gravar(localStorage, 'loja-nao-contar', '1');
    if (params.get('contar') === '1') { try { localStorage.removeItem('loja-nao-contar'); } catch (e) { /* ok */ } }
    if (ler(localStorage, 'loja-nao-contar') === '1') { window.lojaRastro = function () {}; return; }

    function novoId() {
        const b = new Uint8Array(12);
        (window.crypto || {}).getRandomValues ? crypto.getRandomValues(b) : b.forEach((_, i) => { b[i] = Math.random() * 256; });
        return Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
    }
    let visitante = ler(localStorage, 'loja-visitante');
    if (!visitante || !/^[a-f0-9]{24}$/.test(visitante)) { visitante = novoId(); gravar(localStorage, 'loja-visitante', visitante); }

    // de onde veio: vale para a sessão inteira (as páginas seguintes têm a própria loja como referrer)
    function origemDoReferrer() {
        let host = '';
        try { host = document.referrer ? new URL(document.referrer).hostname : ''; } catch (e) { host = ''; }
        if (!host || host === location.hostname) return 'direto';
        const conhecidos = [['whatsapp', 'whatsapp'], ['wa.me', 'whatsapp'], ['instagram', 'instagram'],
            ['facebook', 'facebook'], ['google', 'google'], ['bing', 'bing'], ['t.co', 'twitter'], ['telegram', 'telegram']];
        const achou = conhecidos.find(([trecho]) => host.includes(trecho));
        return achou ? achou[1] : host.replace(/^www\./, '').slice(0, 40);
    }
    let origem = (params.get('o') || params.get('utm_source') || '').toLowerCase().replace(/[^a-z0-9._-]/g, '').slice(0, 40);
    if (origem) gravar(sessionStorage, 'loja-origem', origem);
    else origem = ler(sessionStorage, 'loja-origem') || origemDoReferrer();
    gravar(sessionStorage, 'loja-origem', origem);

    const pagina = document.body.dataset.pagina || 'loja';

    function enviar(tipo, alvo, produto) {
        const corpo = JSON.stringify({v: visitante, o: origem, p: pagina,
            eventos: [{t: tipo, a: alvo ? String(alvo).slice(0, 120) : null, id: produto ? +produto : null}]});
        try {
            if (navigator.sendBeacon && navigator.sendBeacon(url, new Blob([corpo], {type: 'application/json'}))) return;
        } catch (e) { /* cai no fetch */ }
        try { fetch(url, {method: 'POST', body: corpo, headers: {'Content-Type': 'application/json'}, keepalive: true}); }
        catch (e) { /* estatística nunca atrapalha a compra */ }
    }
    window.lojaRastro = enviar;

    enviar('visita', pagina);

    // links e botões marcados com data-rastro="tipo|rótulo" (ex.: data-rastro="whatsapp|Avisar no WhatsApp")
    document.addEventListener('click', ev => {
        const el = ev.target.closest('[data-rastro]');
        if (!el) return;
        const [tipo, alvo] = el.dataset.rastro.split('|');
        enviar(tipo, alvo || el.textContent.trim());
    }, true);
})();
