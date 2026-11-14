/* Combos "leve N por R$ X" — MESMA regra de app/combos.py (mexeu num, mexa no outro).
   itens:  [{id, qtd, preco}]  (só unidades a preço de tabela)
   combos: [{id, nome, quantidade, preco, produtos: [ids]}]
   -> {grupos: [{combo, linhas: [{id, qtd, preco}], tabela, economia}], resto: {id: qtd}} */
(function () {
    'use strict';
    const r2 = v => Math.round((v + Number.EPSILON) * 100) / 100;

    function distribuir(pegar, preco, n) {
        const centavos = Math.round(preco * 100);
        const base = Math.floor(centavos / n), sobra = centavos - base * n;
        const linhas = [];
        let i = 0;
        for (const [id, k] of pegar) {
            for (let j = 0; j < k; j++, i++) {
                const unit = (base + (i >= n - sobra ? 1 : 0)) / 100;
                const ult = linhas[linhas.length - 1];
                if (ult && ult.id === id && ult.preco === unit) ult.qtd += 1;
                else linhas.push({id, qtd: 1, preco: unit});
            }
        }
        return linhas;
    }

    function aplicar(itens, combos) {
        const resto = {}, preco = {};
        for (const it of itens) {
            if (it.qtd > 0) { resto[it.id] = (resto[it.id] || 0) + it.qtd; preco[it.id] = it.preco; }
        }
        const grupos = [];
        const ordem = [...combos].sort((a, b) =>
            (Math.round(a.preco * 100) / a.quantidade - Math.round(b.preco * 100) / b.quantidade) || (a.id - b.id));
        for (const c of ordem) {
            const n = c.quantidade;
            if (n < 1) continue;
            let eleg = [...new Set(c.produtos)].filter(id => resto[id] > 0)
                .sort((a, b) => (preco[b] - preco[a]) || (a - b));
            while (eleg.reduce((s, id) => s + resto[id], 0) >= n) {
                const pegar = [];
                let falta = n;
                for (const id of eleg) {
                    const k = Math.min(resto[id], falta);
                    if (k) { pegar.push([id, k]); falta -= k; }
                    if (!falta) break;
                }
                const tabela = r2(pegar.reduce((s, [id, k]) => s + preco[id] * k, 0));
                if (tabela <= c.preco + 0.004) break;
                pegar.forEach(([id, k]) => { resto[id] -= k; });
                eleg = eleg.filter(id => resto[id] > 0);
                grupos.push({combo: c, linhas: distribuir(pegar, c.preco, n), tabela, economia: r2(tabela - c.preco)});
            }
        }
        Object.keys(resto).forEach(id => { if (!resto[id]) delete resto[id]; });
        return {grupos, resto};
    }

    /* Dica "falta 1 para fechar o combo": para cada combo, quantas unidades elegíveis sobraram fora de combo. */
    function faltando(resto, combos) {
        const dicas = [];
        for (const c of combos) {
            const tem = c.produtos.reduce((s, id) => s + (resto[id] || 0), 0);
            if (tem > 0 && tem < c.quantidade) dicas.push({combo: c, falta: c.quantidade - tem});
        }
        return dicas;
    }

    const api = {aplicar, faltando};
    if (typeof module !== 'undefined') module.exports = api; else window.Combos = api;
})();
