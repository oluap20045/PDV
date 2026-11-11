// Leitor de código de barras pela câmera.
// Motor 1 (todos os aparelhos): BarcodeDetector em WebAssembly — zxing-cpp (pacote barcode-detector 3.2.2 / zxing-wasm 3.1.3,
//   arquivos barcode-detector-ponyfill.js + zxing_reader.wasm servidos localmente), lendo o quadro inteiro em alta resolução.
// Motor 2: BarcodeDetector nativo do navegador, se o WebAssembly não carregar.
// Motor 3 (último recurso): html5-qrcode.
// Uso: PdvScanner.abrir({ continuo: false, onLeitura: (codigo) => {...} })
//   continuo=false -> lê um código e fecha (cadastro)
//   continuo=true  -> fica aberto lendo vários (PDV); o mesmo código só conta de novo após 1,5s
//   qr=true        -> lê QR Code (cupom fiscal)
const PdvScanner = (() => {
    let leitor = null;          // html5-qrcode
    let nativo = null;          // { stream, timer }
    let trilha = null;          // MediaStreamTrack da câmera (lanterna/zoom)
    let modal = null;
    let opcoes = {};
    let ultimo = { codigo: null, quando: 0 };
    let candidato = { codigo: null, vezes: 0 };
    let sessao = 0;             // invalida aberturas antigas se o modal for reaberto rápido

    const FORMATOS_NATIVOS = { barras: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'], qr: ['qr_code'] };
    const formatosLib = () => {
        const F = Html5QrcodeSupportedFormats;
        return opcoes.qr ? [F.QR_CODE] : [F.EAN_13, F.EAN_8, F.UPC_A, F.UPC_E, F.CODE_128];
    };
    const VIDEO = () => ({
        facingMode: { ideal: 'environment' },
        width: { ideal: 1920 }, height: { ideal: 1080 },
        advanced: [{ focusMode: 'continuous' }],
    });

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

    // ---- lanterna e zoom (quando o aparelho deixa)
    function controles() {
        const box = document.getElementById('scanner-controles');
        const bLuz = document.getElementById('scanner-lanterna');
        const bZoom = document.getElementById('scanner-zoom');
        if (!box) return;
        const cap = (trilha && trilha.getCapabilities) ? trilha.getCapabilities() : {};
        bLuz.hidden = !cap.torch;
        bZoom.hidden = !(cap.zoom && cap.zoom.max > 1);
        box.hidden = bLuz.hidden && bZoom.hidden;
        bLuz.classList.remove('active');
        bZoom.textContent = '🔍 Zoom';
    }
    async function aplicar(c) {
        try { await trilha.applyConstraints({ advanced: [c] }); return true; } catch (e) { return false; }
    }
    async function alternarLanterna() {
        const b = document.getElementById('scanner-lanterna');
        const ligar = !b.classList.contains('active');
        if (trilha && await aplicar({ torch: ligar })) b.classList.toggle('active', ligar);
    }
    async function alternarZoom() {
        if (!trilha) return;
        const z = trilha.getCapabilities().zoom;
        const atual = (trilha.getSettings().zoom) || z.min;
        const alvo = atual < Math.min(2, z.max) - 0.01 ? Math.min(2, z.max) : z.min;
        if (await aplicar({ zoom: alvo })) document.getElementById('scanner-zoom').textContent = alvo > z.min ? '🔍 Zoom 2x' : '🔍 Zoom';
    }
    // código de barras pequeno: um pouco de zoom deixa segurar o celular mais longe, onde a câmera foca
    async function zoomInicial() {
        if (opcoes.qr || !trilha || !trilha.getCapabilities) return;
        const z = trilha.getCapabilities().zoom;
        if (z && z.max >= 1.5 && await aplicar({ zoom: Math.max(z.min, 1.5) })) document.getElementById('scanner-zoom').textContent = '🔍 Zoom 1,5x';
    }

    async function parar() {
        sessao++;
        if (nativo) {
            clearTimeout(nativo.timer);
            nativo.stream.getTracks().forEach((t) => t.stop());
            nativo = null;
        }
        if (leitor) {
            try { await leitor.stop(); } catch (e) { /* já parado */ }
            try { leitor.clear(); } catch (e) { /* ok */ }
            leitor = null;
        }
        trilha = null;
        const area = document.getElementById('scanner-leitor');
        if (area) area.innerHTML = '';
    }

    // EAN/UPC: confere o dígito verificador (evita leitura torta)
    function digitoOk(c) {
        if (!/^\d+$/.test(c) || ![8, 12, 13].includes(c.length)) return true;   // outros formatos: sem conferência
        const d = c.split('').map(Number);
        const dv = d.pop();
        const soma = d.reverse().reduce((s, n, i) => s + n * (i % 2 === 0 ? 3 : 1), 0);
        return (10 - (soma % 10)) % 10 === dv;
    }

    function lido(codigo) {
        codigo = (codigo || '').trim();
        if (!codigo || (!opcoes.qr && !digitoOk(codigo))) return;
        // motor da biblioteca erra às vezes: só aceita quando lê o mesmo código 2 vezes seguidas
        if (!nativo && !opcoes.qr) {
            if (candidato.codigo !== codigo) { candidato = { codigo, vezes: 1 }; return; }
            if (++candidato.vezes < 2) return;
        }
        const agora = Date.now();
        if (codigo === ultimo.codigo && agora - ultimo.quando < 1500) return;
        ultimo = { codigo, quando: agora };
        candidato = { codigo: null, vezes: 0 };
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

    // formatos que o leitor nativo do aparelho sabe ler (null = não tem leitor nativo que sirva)
    async function formatosNativos() {
        if (!('BarcodeDetector' in window)) return null;
        try {
            const tem = await BarcodeDetector.getSupportedFormats();
            const quero = opcoes.qr ? FORMATOS_NATIVOS.qr : FORMATOS_NATIVOS.barras;
            return tem.includes(quero[0]) ? quero.filter((f) => tem.includes(f)) : null;
        } catch (e) { return null; }
    }

    // Sem leitor nativo (iPhone etc.): o mesmo leitor em WebAssembly (zxing-cpp), servido pelo próprio PDV
    const BASE_JS = (document.currentScript && document.currentScript.src || '').replace(/[^/]*$/, '');
    let ponyfill = null;
    function carregarPonyfill() {
        if (!ponyfill) ponyfill = new Promise((ok, falha) => {
            const s = document.createElement('script');
            s.src = BASE_JS + 'barcode-detector-ponyfill.js';
            s.onload = () => {
                const api = window.BarcodeDetectionAPI;
                if (!api) return falha(new Error('leitor não carregou'));
                api.prepareZXingModule({
                    overrides: { locateFile: (path, prefix) => (path.endsWith('.wasm') ? BASE_JS + path : prefix + path) },
                });
                ok(api.BarcodeDetector);
            };
            s.onerror = () => { ponyfill = null; falha(new Error('leitor não carregou')); };
            document.head.appendChild(s);
        });
        return ponyfill;
    }

    async function iniciarNativo(minha, formatos, Detector = window.BarcodeDetector) {
        const detector = new Detector({ formats: formatos });
        const stream = await navigator.mediaDevices.getUserMedia({ video: VIDEO(), audio: false });
        if (minha !== sessao) { stream.getTracks().forEach((t) => t.stop()); return; }
        const area = document.getElementById('scanner-leitor');
        area.innerHTML = '<div class="scanner-video"><video playsinline muted autoplay></video><div class="scanner-mira"></div></div>';
        area.querySelector('.scanner-mira').classList.toggle('qr', !!opcoes.qr);
        const video = area.querySelector('video');
        video.srcObject = stream;
        await video.play().catch(() => {});
        nativo = { stream, timer: null };
        trilha = stream.getVideoTracks()[0];
        const ciclo = async () => {
            if (!nativo || minha !== sessao) return;
            try {
                if (video.readyState >= 2) {
                    const achados = await detector.detect(video);
                    if (achados.length && minha === sessao) lido(achados[0].rawValue);
                }
            } catch (e) { /* quadro ruim: tenta o próximo */ }
            if (nativo) nativo.timer = setTimeout(ciclo, 80);
        };
        ciclo();
    }

    async function iniciarBiblioteca(minha) {
        leitor = new Html5Qrcode('scanner-leitor', {
            formatsToSupport: formatosLib(),
            experimentalFeatures: { useBarCodeDetectorIfSupported: true },
            verbose: false,
        });
        await leitor.start(
            { facingMode: 'environment' },
            {
                fps: 15,
                disableFlip: true,
                videoConstraints: VIDEO(),
                qrbox: (w, h) => opcoes.qr
                    ? { width: Math.floor(Math.min(w, h) * 0.8), height: Math.floor(Math.min(w, h) * 0.8) }   // QR: quadrado
                    : { width: Math.floor(w * 0.9), height: Math.floor(Math.min(h, w) * 0.5) },              // barras: faixa larga
            },
            lido,
            () => {}  // erro por quadro sem código: normal, ignora
        );
        if (minha !== sessao) return;
        const video = document.querySelector('#scanner-leitor video');
        trilha = video && video.srcObject ? video.srcObject.getVideoTracks()[0] : null;
    }

    async function abrir(o) {
        opcoes = o || {};
        ultimo = { codigo: null, quando: 0 };
        candidato = { codigo: null, vezes: 0 };
        if (!window.isSecureContext) {
            alert('A câmera só funciona com HTTPS. Acesse por https://pdv.local');
            return;
        }
        const el = document.getElementById('scanner-modal');
        modal = bootstrap.Modal.getOrCreateInstance(el);
        document.getElementById('scanner-titulo').textContent =
            opcoes.qr ? 'Ler QR Code do cupom' : (opcoes.continuo ? 'Bipar produtos' : 'Ler código de barras');
        status('Abrindo câmera...');
        modal.show();

        await parar();
        const minha = sessao;
        try {
            // 1º zxing em WebAssembly (o que melhor leu código pequeno/fora de foco nos testes),
            // 2º leitor nativo do navegador, 3º biblioteca antiga
            let Detector = null;
            try { Detector = await carregarPonyfill(); } catch (e) { /* sem WebAssembly */ }
            if (minha !== sessao) return;
            const formatos = Detector ? null : await formatosNativos();
            if (Detector) await iniciarNativo(minha, opcoes.qr ? FORMATOS_NATIVOS.qr : FORMATOS_NATIVOS.barras, Detector);
            else if (formatos) await iniciarNativo(minha, formatos);
            else await iniciarBiblioteca(minha);
            if (minha !== sessao) return;
            controles();
            await zoomInicial();
            status(opcoes.qr ? 'Aponte para o QR Code' : 'Aponte para o código de barras, a um palmo de distância');
        } catch (e) {
            status('Não consegui abrir a câmera: ' + (e.message || e) +
                   '. Verifique a permissão de câmera do navegador.', 'danger');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const el = document.getElementById('scanner-modal');
        if (el) el.addEventListener('hidden.bs.modal', parar);
        const luz = document.getElementById('scanner-lanterna');
        const zoom = document.getElementById('scanner-zoom');
        if (luz) luz.addEventListener('click', alternarLanterna);
        if (zoom) zoom.addEventListener('click', alternarZoom);
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

// Botão 👁 ao lado de campos de senha: mostra/esconde o que foi digitado
document.addEventListener('click', (ev) => {
    const botao = ev.target.closest && ev.target.closest('[data-mostrar-senha]');
    if (!botao) return;
    const campo = document.getElementById(botao.dataset.mostrarSenha);
    if (!campo) return;
    const mostrar = campo.type === 'password';
    campo.type = mostrar ? 'text' : 'password';
    botao.setAttribute('aria-label', mostrar ? 'Esconder senha' : 'Mostrar senha');
    campo.focus();
});
