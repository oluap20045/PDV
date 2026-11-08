// Sugestão de preço: preço = custo / (1 - margem - taxa máx. do cartão), arredondado p/ cima nos 10 centavos.
// Uso: <div class="sugestao-preco" data-custo="#custo" data-preco="#preco"></div> e window.PRECO = {margem, taxa, taxa_desc}
const PdvPreco = (() => {
    const num = (t) => { t = String(t ?? '').trim(); if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.'); const v = parseFloat(t); return isNaN(v) ? 0 : v; };
    const brl = (v) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    const pct = (v) => v.toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + '%';

    function sugerido(custo, p = window.PRECO) {
        const div = 1 - (p.margem + p.taxa) / 100;
        if (!(custo > 0) || div <= 0.05) return null;
        return Math.ceil(Math.round(custo / div * 10 * 1e6) / 1e6) / 10;
    }

    // margem que sobra de verdade com esse preço, no pior caso (maior taxa)
    function margemReal(custo, preco, p = window.PRECO) {
        if (!(preco > 0)) return null;
        return (1 - p.taxa / 100 - custo / preco) * 100;
    }

    function montar(box) {
        const custoEl = document.querySelector(box.dataset.custo);
        const precoEl = document.querySelector(box.dataset.preco);
        const p = window.PRECO;
        const atualizar = () => {
            const custo = num(custoEl.value);
            const s = sugerido(custo);
            if (s === null) { box.innerHTML = '<span class="text-muted">💡 Informe o custo para ver o preço sugerido.</span>'; return; }
            const preco = num(precoEl.value);
            const real = margemReal(custo, preco);
            const explica = `custo ${brl(custo)} ÷ (1 − ${pct(p.margem)} margem − ${pct(p.taxa)} taxa)`;
            let aviso = '';
            if (preco > 0 && real !== null && real < p.margem - 0.05) {
                aviso = `<div class="${real < 0 ? 'text-danger fw-semibold' : 'text-warning-emphasis'}">⚠ Com ${brl(preco)} sobram ${pct(Math.round(real * 10) / 10)} ${real < 0 ? '(prejuízo!)' : ''} no pior caso.</div>`;
            }
            box.innerHTML = `💡 Sugerido: <strong>${brl(s)}</strong>
                <button type="button" class="btn btn-link btn-sm p-0 align-baseline usar-sugestao">usar</button>
                <div class="text-muted">${explica}${p.taxa_desc ? ` · maior taxa: ${p.taxa_desc}` : ' · nenhuma taxa de cartão cadastrada'}</div>${aviso}`;
            box.querySelector('.usar-sugestao').onclick = () => { precoEl.value = s.toFixed(2); atualizar(); };
        };
        custoEl.addEventListener('input', atualizar);
        precoEl.addEventListener('input', atualizar);
        atualizar();
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (window.PRECO) document.querySelectorAll('.sugestao-preco').forEach(montar);
    });
    return { sugerido, margemReal, num };
})();
