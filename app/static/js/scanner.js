// Leitor de código de barras pela câmera (usa html5-qrcode, servido localmente).
// Uso: PdvScanner.abrir({ continuo: false, onLeitura: (codigo) => {...} })
//   continuo=false -> lê um código e fecha (cadastro)
//   continuo=true  -> fica aberto lendo vários (PDV); o mesmo código só conta de novo após 1,5s
const PdvScanner = (() => {
    let leitor = null;
    let modal = null;
    let opcoes = {};
    let ultimo = { codigo: null, quando: 0 };

    const formatos = () => {
        const F = Html5QrcodeSupportedFormats;
        return [F.EAN_13, F.EAN_8, F.UPC_A, F.UPC_E, F.CODE_128, F.CODE_39, F.ITF, F.QR_CODE];
    };

    function bipe() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.frequency.value = 1800;
            gain.gain.value = 0.15;
            osc.connect(gain); gain.connect(ctx.destination);
            osc.start(); osc.stop(ctx.currentTime + 0.12);
            osc.onended = () => ctx.close();
        } catch (e) { /* sem áudio, segue */ }
        if (navigator.vibrate) navigator.vibrate(80);
    }

    function status(texto, tipo = 'secondary') {
        const el = document.getElementById('scanner-status');
        el.className = `small mt-2 text-${tipo}`;
        el.textContent = texto;
    }

    async function parar() {
        if (leitor) {
            try { await leitor.stop(); } catch (e) { /* já parado */ }
            try { leitor.clear(); } catch (e) { /* ok */ }
            leitor = null;
        }
    }

    async function lido(codigo) {
        const agora = Date.now();
        if (codigo === ultimo.codigo && agora - ultimo.quando < 1500) return;
        ultimo = { codigo, quando: agora };
        if (!opcoes.continuo) {
            modal.hide();               // o evento hidden para a câmera
        }
        // onLeitura pode devolver nada, um texto, ou {texto, ok}
        let r = opcoes.onLeitura ? opcoes.onLeitura(codigo) : null;
        if (typeof r === 'string') r = { texto: r, ok: true };
        r = r || { texto: `Lido: ${codigo}`, ok: true };
        if (r.ok) bipe(); else if (navigator.vibrate) navigator.vibrate([60, 60, 60]);
        if (opcoes.continuo) status(r.texto, r.ok ? 'success' : 'danger');
    }

    async function abrir(o) {
        opcoes = o || {};
        ultimo = { codigo: null, quando: 0 };
        if (!window.isSecureContext) {
            alert('A câmera só funciona com HTTPS. Acesse por https://pdv.local');
            return;
        }
        const el = document.getElementById('scanner-modal');
        modal = bootstrap.Modal.getOrCreateInstance(el);
        document.getElementById('scanner-titulo').textContent =
            opcoes.continuo ? 'Bipar produtos' : 'Ler código de barras';
        status('Abrindo câmera...');
        modal.show();

        await parar();
        leitor = new Html5Qrcode('scanner-leitor', {
            formatsToSupport: formatos(),
            experimentalFeatures: { useBarCodeDetectorIfSupported: true },
            verbose: false,
        });
        try {
            await leitor.start(
                { facingMode: 'environment' },
                { fps: 10, qrbox: (w, h) => ({ width: Math.floor(w * 0.85), height: Math.floor(Math.min(h, w) * 0.45) }) },
                lido,
                () => {}  // erro por frame sem código: normal, ignora
            );
            status('Aponte para o código de barras');
        } catch (e) {
            status('Não consegui abrir a câmera: ' + (e.message || e) +
                   '. Verifique a permissão de câmera do navegador.', 'danger');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const el = document.getElementById('scanner-modal');
        if (el) el.addEventListener('hidden.bs.modal', parar);
    });

    return { abrir, bipe };
})();

// Leitor USB/Bluetooth "digita" o código e manda Enter: no campo de código do cadastro,
// o Enter não pode enviar o formulário pela metade — só pula para o próximo campo.
document.addEventListener('keydown', (ev) => {
    const alvo = ev.target;
    if (ev.key !== 'Enter' || !alvo.matches || !alvo.matches('form input[name="codigo_barras"]')) return;
    ev.preventDefault();
    const campos = Array.from(alvo.form.querySelectorAll('input:not([type=hidden]), select'));
    const prox = campos[campos.indexOf(alvo) + 1];
    if (prox) prox.focus();
});
