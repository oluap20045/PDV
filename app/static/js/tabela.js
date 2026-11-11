// Tabelas ordenáveis: <table data-ordenavel> com <th data-ordem="num|texto">.
// O valor de cada célula vem de data-v (se houver) ou do texto. Clicar no título alterna ▲/▼.
// data-ordem-inicial="desc" no <th> marca a ordenação com que a tabela já vem do servidor.
(() => {
    const comparador = new Intl.Collator('pt-BR', { sensitivity: 'base', numeric: true });

    function valor(td, tipo) {
        const bruto = td ? (td.dataset.v ?? td.textContent.trim()) : '';
        if (tipo !== 'num') return bruto;
        let t = String(bruto).replace(/[^\d,.\-]/g, '');
        if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
        const n = parseFloat(t);
        return isNaN(n) ? -Infinity : n;
    }

    function ordenar(tabela, th, sentido) {
        const ths = [...th.parentElement.children];
        const col = ths.indexOf(th);
        const tipo = th.dataset.ordem;
        const corpo = tabela.tBodies[0];
        const linhas = [...corpo.rows];
        linhas.sort((a, b) => {
            const va = valor(a.cells[col], tipo), vb = valor(b.cells[col], tipo);
            const r = tipo === 'num' ? va - vb : comparador.compare(va, vb);
            return sentido === 'asc' ? r : -r;
        });
        linhas.forEach((tr) => corpo.appendChild(tr));
        ths.forEach((t) => {
            if (!t.dataset.ordem) return;
            t.setAttribute('aria-sort', t === th ? (sentido === 'asc' ? 'ascending' : 'descending') : 'none');
            const seta = t.querySelector('.seta');
            if (seta) seta.textContent = t === th ? (sentido === 'asc' ? '▲' : '▼') : '';
        });
    }

    function preparar(tabela) {
        tabela.querySelectorAll('th[data-ordem]').forEach((th) => {
            const botao = document.createElement('button');
            botao.type = 'button';
            botao.className = 'btn-ordenar';
            botao.innerHTML = th.innerHTML + ' <span class="seta" aria-hidden="true"></span>';
            th.innerHTML = '';
            th.appendChild(botao);
            th.setAttribute('aria-sort', 'none');
            if (th.dataset.ordemInicial) {
                th.setAttribute('aria-sort', th.dataset.ordemInicial === 'asc' ? 'ascending' : 'descending');
                botao.querySelector('.seta').textContent = th.dataset.ordemInicial === 'asc' ? '▲' : '▼';
            }
            botao.addEventListener('click', () => {
                const atual = th.getAttribute('aria-sort');
                // 1º clique: números do maior pro menor, texto de A a Z
                const sentido = atual === 'none' ? (th.dataset.ordem === 'num' ? 'desc' : 'asc')
                                                 : (atual === 'ascending' ? 'desc' : 'asc');
                ordenar(tabela, th, sentido);
            });
        });
    }

    document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('table[data-ordenavel]').forEach(preparar));
})();
