// "Enviar PDF": abre o compartilhar do celular com o PDF anexado (WhatsApp, e-mail...).
// O iPhone só deixa compartilhar arquivo dentro do toque do usuário; por isso o PDF é
// baixado antes (data-prefetch) ou no 1º toque — se o 1º toque não puder, o 2º funciona.
(() => {
    const cache = new Map();

    async function arquivo(btn) {
        const url = btn.dataset.pdf;
        if (!cache.has(url)) {
            cache.set(url, fetch(url).then((r) => {
                if (!r.ok) throw new Error('não consegui gerar o PDF');
                return r.blob();
            }).then((b) => new File([b], btn.dataset.nome, { type: 'application/pdf' })));
        }
        return cache.get(url);
    }

    function baixar(file) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(file);
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    }

    document.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('.btn-compartilhar-pdf');
        if (!btn) return;
        const original = btn.textContent;
        try {
            btn.disabled = true;
            btn.textContent = 'Preparando...';
            const file = await arquivo(btn);
            if (navigator.canShare && navigator.canShare({ files: [file] })) {
                await navigator.share({ files: [file], title: file.name, text: btn.dataset.texto });
            } else {
                baixar(file);   // computador: baixa o PDF para anexar no WhatsApp Web
            }
        } catch (e) {
            if (e.name === 'NotAllowedError') {
                btn.textContent = 'Toque de novo para enviar';
                btn.disabled = false;
                return;
            }
            if (e.name !== 'AbortError') alert('Não foi possível enviar: ' + e.message);
        }
        btn.disabled = false;
        btn.textContent = original;
    });

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.btn-compartilhar-pdf[data-prefetch]').forEach((b) => arquivo(b).catch(() => {}));
    });
})();
