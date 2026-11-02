/* Bravo PDF: janelas de diálogo (salvar, assinar, certificado, OCR, marca d'água, dividir, comparar...). */
'use strict';

function dialogo({ titulo, corpo, botoes = [{ texto: 'OK', valor: 'ok', primario: true }], largura, aoAbrir, validar }) {
  return new Promise(resolve => {
    const d = $('#dlg'), f = $('#dlgForm');
    if (d.open) d.close('');
    d.style.width = largura ? `min(${largura}px, 94vw)` : '';
    const pe = el('div', { class: 'dlg-pe' });
    for (const b of botoes) {
      const bt = el('button', { class: 'btn' + (b.primario ? ' primario' : '') + (b.perigo ? ' perigo' : ''), value: b.valor, type: 'submit', text: b.texto });
      if (b.valor === '') bt.setAttribute('formnovalidate', '');
      pe.append(bt);
    }
    f.replaceChildren(
      el('div', { class: 'dlg-cab' }, el('h2', { text: titulo }), el('button', { class: 'ico so-ico', value: '', type: 'submit', formnovalidate: true, title: 'Fechar' }, icone('fechar'))),
      el('div', { class: 'dlg-corpo' }, ...corpo), pe);
    const aoEnviar = ev => {
      const v = ev.submitter ? ev.submitter.value : '';
      if (v && validar) {
        const msg = validar(v);
        if (msg) { ev.preventDefault(); aviso(msg, 'erro'); return; }
      }
    };
    f.onsubmit = aoEnviar;
    d.onclose = () => { d.onclose = null; resolve(d.returnValue || null); };
    d.returnValue = '';
    d.showModal();
    if (aoAbrir) aoAbrir(f);
  });
}
const L = (txt, campo, extra = {}) => el('label', { class: 'l', ...extra }, txt, campo);
const CHK = (txt, attrs = {}) => { const i = el('input', { type: 'checkbox', ...attrs }); return [el('label', { class: 'check' }, i, el('span', {}, txt)), i]; };

/* ---------------------------------------------------------------- projeto para o servidor */
function limparItem(i) {
  const c = { ...i };
  delete c.id; delete c._agora;
  return c;
}
function montarProjeto(opcoes = {}, paginas = E.paginas) {
  const mapa = new Map(E.paginas.map((p, k) => [p.uid, k]));
  const novoIndice = new Map(paginas.map((p, k) => [mapa.get(p.uid), k]));
  const decor = {};
  for (const [k, v] of Object.entries(E.decor)) {
    if (!v) continue;
    decor[k] = { ...v };
    if (v.paginas) decor[k].paginas = v.paginas.filter(i => novoIndice.has(i)).map(i => novoIndice.get(i));
  }
  const usados = new Set(paginas.map(p => p.doc));
  const campos = {};
  for (const [d, v] of Object.entries(E.campos)) if (usados.has(d)) campos[d] = v;
  return {
    paginas: paginas.map(p => ({
      doc: p.doc, p: p.p, rot: p.rot, w: p.w, h: p.h,
      itens: p.itens.filter(i => i.tipo !== 'tarja').map(limparItem),
      tarjas: p.itens.filter(i => i.tipo === 'tarja').map(i => ({ x: i.x, y: i.y, w: i.w, h: i.h })),
    })),
    campos, decor, opcoes: { nome: E.nome, ...opcoes },
  };
}
function retParaFinal(r, pg) {
  const b = dimsBase(pg);
  const pts = [[r.x, r.y], [r.x + r.w, r.y + r.h]].map(([x, y]) => {
    switch (pg.rot) {
      case 90: return [b.h - y, x];
      case 180: return [b.w - x, b.h - y];
      case 270: return [y, b.w - x];
      default: return [x, y];
    }
  });
  const x = Math.min(pts[0][0], pts[1][0]), y = Math.min(pts[0][1], pts[1][1]);
  return { x, y, w: Math.abs(pts[1][0] - pts[0][0]), h: Math.abs(pts[1][1] - pts[0][1]) };
}

/* ---------------------------------------------------------------- salvar */
async function dialogoSalvar({ comprimir = 'nao', senha = false, paginas = null, titulo = 'Salvar PDF' } = {}) {
  if (!E.paginas.length) return;
  fecharEditores();
  const pgs = paginas || E.paginas;
  const nome = el('input', { type: 'text', value: nomeBase(E.nome) + (paginas ? ' - páginas' : '') + '.pdf', required: true });
  const nAnot = pgs.reduce((n, p) => n + p.itens.filter(i => i.tipo !== 'tarja').length, 0);
  const nTarja = pgs.reduce((n, p) => n + p.itens.filter(i => i.tipo === 'tarja').length, 0);
  const temCampos = pgs.some(p => E.docs[p.doc] && E.docs[p.doc].campos && E.docs[p.doc].campos.length);
  const modo = el('select', {}, el('option', { value: 'editavel', text: 'Editáveis (dá para mexer em outros programas)' }), el('option', { value: 'incorporar', text: 'Incorporadas à página (ninguém altera)' }));
  const comp = el('select', {}, ...[['nao', 'Sem compressão (qualidade máxima)'], ['leve', 'Leve'], ['media', 'Média (bom para e-mail)'], ['forte', 'Forte (arquivo bem menor)']].map(([v, t]) => el('option', { value: v, text: t })));
  comp.value = comprimir;
  const cert = E.certificado && E.certificado.info ? E.certificado : null;
  const [lSenha, cSenha] = CHK('Proteger com senha (pedida para abrir o arquivo)', { disabled: cert ? true : null });
  const s1 = el('input', { type: 'password', autocomplete: 'new-password', placeholder: 'Senha' });
  const s2 = el('input', { type: 'password', autocomplete: 'new-password', placeholder: 'Repita a senha' });
  const caixaSenha = el('div', { class: 'grade2' }, s1, s2);
  caixaSenha.hidden = !senha;
  cSenha.checked = senha && !cert;
  cSenha.addEventListener('change', () => { caixaSenha.hidden = !cSenha.checked; if (cSenha.checked) s1.focus(); });
  const [lMeta, cMeta] = CHK('Remover informações ocultas (autor, programa e datas)');
  const corpo = [L('Nome do arquivo', nome)];
  if (nAnot || temCampos) corpo.push(L(`Anotações${temCampos ? ' e formulário' : ''}`, modo));
  corpo.push(L('Comprimir', comp), lSenha, caixaSenha, lMeta);
  if (nTarja) corpo.push(el('p', { class: 'dica alerta', text: `${nTarja} tarja(s): as páginas com tarja viram imagem e o conteúdo sob a tarja deixa de existir no arquivo. As informações ocultas também são removidas.` }));
  if (cert) corpo.push(el('p', { class: 'dica', text: `O arquivo será assinado digitalmente por ${cert.info.nome}. Para assinar, o PDF não pode ter senha.` }));
  if (cSenha.checked) setTimeout(() => s1.focus(), 50);
  const r = await dialogo({
    titulo, corpo, botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Salvar', valor: 'ok', primario: true }],
    validar: () => {
      if (!nome.value.trim()) return 'Dê um nome ao arquivo.';
      if (cSenha.checked && !s1.value) return 'Digite a senha.';
      if (cSenha.checked && s1.value !== s2.value) return 'As senhas não são iguais.';
      return '';
    },
  });
  if (r !== 'ok') return;
  let arquivo = nome.value.trim();
  if (!/\.pdf$/i.test(arquivo)) arquivo += '.pdf';
  const opcoes = { incorporar: modo.value === 'incorporar', comprimir: comp.value, senha: cSenha.checked ? s1.value : '', limpar_metadados: cMeta.checked };
  const projeto = montarProjeto(opcoes, pgs);
  let assinatura = null;
  if (cert) {
    assinatura = { pfx: cert.pfx, senha: cert.senha, motivo: cert.motivo, local: cert.local, imagem: cert.comImagem ? E.assinaturaAtiva : null, pagina: 0, caixa: null };
    if (cert.caixa) {
      const k = pgs.findIndex(p => p.uid === cert.caixa.pg);
      if (k >= 0) { assinatura.pagina = k; assinatura.caixa = retParaFinal(cert.caixa, pgs[k]); }
    }
  }
  try {
    const blob = await ocupado('Gerando o PDF…', t => api('/api/salvar', { metodo: 'POST', json: { projeto, assinatura, tarefa: t }, tipo: 'blob' }), true);
    if (await salvarArquivo(blob, arquivo, 'pdf')) {
      if (!paginas) E.nome = arquivo;
      $('#nomeDoc').value = E.nome;
      E.salvoEm = E.hist.length;
      aviso(`Pronto: ${arquivo} (${(blob.size / 1024 / 1024).toFixed(blob.size > 1048576 ? 1 : 2)} MB).`, 'ok');
    }
  } catch (e) { erro(e); }
}

/* ---------------------------------------------------------------- assinatura visual */
const FONTES_MANUSCRITAS = ['Segoe Script', 'Brush Script MT', 'Lucida Handwriting', 'Snell Roundhand', 'Apple Chancery', 'Bradley Hand', 'Savoye LET', 'URW Chancery L', 'Z003', 'Comic Sans MS'];

function aparar(canvas, folga = 8) {
  const ctx = canvas.getContext('2d');
  const { width: w, height: h } = canvas;
  const d = ctx.getImageData(0, 0, w, h).data;
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (d[(y * w + x) * 4 + 3] > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  }
  if (x1 < 0) return null;
  x0 = Math.max(0, x0 - folga); y0 = Math.max(0, y0 - folga); x1 = Math.min(w - 1, x1 + folga); y1 = Math.min(h - 1, y1 + folga);
  const c = document.createElement('canvas');
  c.width = x1 - x0 + 1; c.height = y1 - y0 + 1;
  c.getContext('2d').drawImage(canvas, x0, y0, c.width, c.height, 0, 0, c.width, c.height);
  return c.toDataURL('image/png');
}

async function dialogoAssinatura() {
  let aba = 'desenhar';
  const cores = { '#1b2a6b': 'Azul', '#111111': 'Preta' };
  let corTinta = '#1b2a6b';
  const tela = el('canvas', { class: 'desenho', width: 1000, height: 340 });
  const ctx = tela.getContext('2d');
  let desenhou = false;
  const desenho = el('div', {}, tela, el('div', { class: 'linha-props', style: 'margin-top:8px' },
    ...Object.entries(cores).map(([c, n]) => el('button', { type: 'button', class: 'btn mini', onclick: () => { corTinta = c; }, text: n })),
    el('button', { type: 'button', class: 'btn mini', style: 'margin-left:auto', onclick: () => { ctx.clearRect(0, 0, tela.width, tela.height); desenhou = false; }, text: 'Limpar' })));
  let ult = null;
  const pos = e => { const r = tela.getBoundingClientRect(); return [(e.clientX - r.left) * tela.width / r.width, (e.clientY - r.top) * tela.height / r.height, e.pressure || 0.5]; };
  tela.addEventListener('pointerdown', e => { tela.setPointerCapture(e.pointerId); ult = pos(e); desenhou = true; });
  tela.addEventListener('pointermove', e => {
    if (!ult) return;
    const p = pos(e);
    ctx.strokeStyle = corTinta; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.lineWidth = 3.2 + (e.pointerType === 'pen' ? p[2] * 4 : 1.5);
    ctx.beginPath(); ctx.moveTo(ult[0], ult[1]); ctx.lineTo(p[0], p[1]); ctx.stroke();
    ult = p;
  });
  tela.addEventListener('pointerup', () => { ult = null; });

  const nome = el('input', { type: 'text', placeholder: 'Seu nome', maxlength: 60 });
  const fontes = FONTES_MANUSCRITAS.filter(f => { try { return document.fonts.check(`32px "${f}"`) && f; } catch (_) { return false; } });
  const fontesUsar = fontes.length ? fontes : ['cursive'];
  let fonteEscolhida = fontesUsar[0];
  const opcoesFonte = el('div', { class: 'assin-lista' });
  const desenharDigitada = () => {
    opcoesFonte.replaceChildren(...fontesUsar.slice(0, 6).map(f => el('div', { class: 'assin', role: 'button', 'aria-pressed': String(f === fonteEscolhida), onclick: () => { fonteEscolhida = f; desenharDigitada(); } },
      el('span', { style: `font:40px "${f}", cursive;color:${corTinta};padding:4px 10px`, text: nome.value || 'Seu nome' }))));
  };
  nome.addEventListener('input', desenharDigitada);
  desenharDigitada();
  const digitar = el('div', {}, L('Nome', nome), opcoesFonte);

  const arq = el('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp' });
  const previa = el('div', { class: 'previa-assin' }, el('span', { class: 'muted', text: 'Nenhuma imagem' }));
  const [lFundo, cFundo] = CHK('Tirar o fundo branco (para foto da assinatura em papel)');
  cFundo.checked = true;
  let imgCarregada = null;
  const prepararImagem = () => {
    if (!imgCarregada) return null;
    const c = document.createElement('canvas');
    const esc = Math.min(1, 1400 / imgCarregada.naturalWidth);
    c.width = imgCarregada.naturalWidth * esc; c.height = imgCarregada.naturalHeight * esc;
    const x = c.getContext('2d');
    x.drawImage(imgCarregada, 0, 0, c.width, c.height);
    if (cFundo.checked) {
      const d = x.getImageData(0, 0, c.width, c.height);
      for (let i = 0; i < d.data.length; i += 4) {
        const lum = 0.299 * d.data[i] + 0.587 * d.data[i + 1] + 0.114 * d.data[i + 2];
        if (lum > 175) d.data[i + 3] = 0;
        else if (lum > 120) d.data[i + 3] = Math.round(255 * (175 - lum) / 55);
      }
      x.putImageData(d, 0, 0);
    }
    return aparar(c, 4);
  };
  const mostrarPrevia = () => { const u = prepararImagem(); previa.replaceChildren(u ? el('img', { src: u, alt: '' }) : el('span', { class: 'muted', text: 'Nenhuma imagem' })); };
  arq.addEventListener('change', async () => {
    const f = arq.files[0];
    if (!f) return;
    const im = new Image();
    im.onload = () => { imgCarregada = im; mostrarPrevia(); };
    im.src = await lerArquivo(f, 'dataurl');
  });
  cFundo.addEventListener('change', mostrarPrevia);
  const imagem = el('div', {}, L('Imagem da assinatura', arq), lFundo, previa);

  const paineis = { desenhar: desenho, digitar, imagem };
  const abas = el('div', { class: 'abas-dlg' });
  const trocar = a => {
    aba = a;
    for (const [k, p] of Object.entries(paineis)) p.hidden = k !== a;
    $$('button', abas).forEach(b => b.setAttribute('aria-pressed', String(b.dataset.a === a)));
  };
  for (const [k, t] of [['desenhar', 'Desenhar'], ['digitar', 'Digitar'], ['imagem', 'Imagem']]) abas.append(el('button', { type: 'button', 'data-a': k, onclick: () => trocar(k), text: t }));
  trocar('desenhar');
  const [lGuardar, cGuardar] = CHK('Guardar neste computador para usar de novo');
  const r = await dialogo({
    titulo: 'Nova assinatura', largura: 620,
    corpo: [abas, desenho, digitar, imagem, lGuardar, el('p', { class: 'muted small', text: 'A assinatura fica só no seu computador.' })],
    botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Usar assinatura', valor: 'ok', primario: true }],
    validar: () => {
      if (aba === 'desenhar' && !desenhou) return 'Desenhe a assinatura no quadro.';
      if (aba === 'digitar' && !nome.value.trim()) return 'Digite seu nome.';
      if (aba === 'imagem' && !imgCarregada) return 'Escolha uma imagem.';
      return '';
    },
  });
  if (r !== 'ok') { if (!E.assinaturaAtiva && E.ferramenta === 'assinatura') escolherFerramenta('selecionar'); return; }
  let url = null;
  if (aba === 'desenhar') url = aparar(tela);
  else if (aba === 'imagem') url = prepararImagem();
  else {
    const c = document.createElement('canvas');
    c.width = 1400; c.height = 300;
    const x = c.getContext('2d');
    x.font = `150px "${fonteEscolhida}", cursive`;
    x.fillStyle = corTinta;
    x.textBaseline = 'middle';
    x.fillText(nome.value.trim(), 20, 160, 1360);
    url = aparar(c);
  }
  if (!url) return aviso('A assinatura ficou vazia.', 'erro');
  E.assinaturaAtiva = url;
  if (cGuardar.checked) {
    E.prefs.assinaturas = [url, ...(E.prefs.assinaturas || []).filter(a => a !== url)].slice(0, 6);
    await salvarPrefs();
  }
  if (E.ferramenta !== 'assinatura') escolherFerramenta('assinatura');
  else renderProps();
  aviso('Clique na página onde quer assinar.', '', 3500);
}

async function escolherImagem() {
  const inp = el('input', { type: 'file', accept: 'image/png,image/jpeg,image/webp,image/gif' });
  inp.addEventListener('change', async () => {
    const f = inp.files[0];
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) return aviso('Imagem grande demais (máximo 20 MB).', 'erro');
    E.imagemAtiva = await lerArquivo(f, 'dataurl');
    if (E.ferramenta !== 'imagem') escolherFerramenta('imagem');
    renderProps();
    aviso('Clique na página onde quer colocar a imagem.', '', 3500);
  });
  inp.click();
}

/* ---------------------------------------------------------------- certificado digital */
async function dialogoCertificado() {
  const c = E.certificado || {};
  const arq = el('input', { type: 'file', accept: '.pfx,.p12,application/x-pkcs12' });
  const senha = el('input', { type: 'password', autocomplete: 'off', placeholder: 'Senha do certificado' });
  const info = el('div');
  let pfx = c.pfx || null, dados = c.info || null;
  const mostrar = () => {
    if (!dados) { info.replaceChildren(); return; }
    info.replaceChildren(el('div', { class: 'cert-info' }, el('b', { text: dados.nome }),
      dados.documento ? el('div', { text: dados.documento }) : '',
      el('div', { class: 'muted', text: `Emitido por: ${dados.emissor.replace(/^.*?CN=([^,]+).*$/, '$1')}` }),
      el('div', { class: 'muted', text: `Válido de ${dados.valido_de} até ${dados.valido_ate}` }),
      el('div', {}, el('span', { class: 'selo' + (dados.icp_brasil ? ' ok' : ''), text: dados.icp_brasil ? 'ICP-Brasil' : 'Fora da ICP-Brasil' }), ' ',
        dados.vencido ? el('span', { class: 'selo ruim', text: 'Fora da validade' }) : '')));
  };
  mostrar();
  const verificar = async () => {
    const f = arq.files[0];
    if (!f && !pfx) return aviso('Escolha o arquivo do certificado (.pfx ou .p12).', 'erro');
    try {
      if (f) pfx = base64DeBuffer(await lerArquivo(f));
      dados = await api('/api/certificado', { metodo: 'POST', json: { pfx, senha: senha.value } });
      mostrar();
    } catch (e) { dados = null; mostrar(); erro(e); }
  };
  const btVer = el('button', { type: 'button', class: 'btn', onclick: verificar, text: 'Ler certificado' });
  senha.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); verificar(); } });
  const motivo = el('input', { type: 'text', value: c.motivo || 'Concordo com o conteúdo do documento', maxlength: 200 });
  const local = el('input', { type: 'text', value: c.local || '', maxlength: 120, placeholder: 'Cidade' });
  const vis = el('select', {}, el('option', { value: 'visivel', text: 'Visível: um selo na página' }), el('option', { value: 'invisivel', text: 'Invisível (só no painel de assinaturas)' }));
  vis.value = c.caixa === null && c.info ? 'invisivel' : 'visivel';
  const [lImg, cImg] = CHK('Mostrar minha assinatura desenhada no selo', { disabled: E.assinaturaAtiva ? null : true });
  cImg.checked = !!c.comImagem;
  const r = await dialogo({
    titulo: 'Assinar com certificado digital', largura: 560,
    corpo: [el('p', { class: 'dica', text: 'Use um certificado A1 (arquivo .pfx ou .p12), como os e-CPF e e-CNPJ da ICP-Brasil. O arquivo e a senha ficam só na memória enquanto o app está aberto e não são guardados. A assinatura é aplicada quando você salvar.' }),
      L('Arquivo do certificado', arq), el('div', { class: 'linha-props', style: 'margin-bottom:12px' }, senha, btVer), info,
      el('div', { class: 'grade2' }, L('Motivo', motivo), L('Local', local)), L('Aparência', vis), lImg],
    botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Confirmar', valor: 'ok', primario: true }],
    validar: () => (!dados ? 'Leia o certificado com a senha antes de confirmar.' : dados.vencido ? 'Este certificado está fora da validade.' : ''),
  });
  if (r !== 'ok') { if (E.ferramenta === 'certificado' && !(E.certificado && E.certificado.info)) escolherFerramenta('selecionar'); return; }
  let caixa = c.caixa || null;
  if (vis.value === 'invisivel') caixa = null;
  else if (!caixa) {
    const pg = E.paginas[E.atual];
    const b = dimsBase(pg);
    caixa = { pg: pg.uid, x: b.w - 250, y: b.h - 100, w: 220, h: 64 };
  }
  E.certificado = { pfx, senha: senha.value || c.senha || '', info: dados, motivo: motivo.value, local: local.value, comImagem: cImg.checked, caixa };
  renderFaixas();
  E.paginas.forEach(p => atualizarPagina(p.uid));
  if (caixa) {
    if (E.ferramenta !== 'certificado') escolherFerramenta('certificado');
    aviso('O selo aparece no canto da página. Para mudar o lugar, arraste na página. Ele é aplicado ao salvar.', '', 6000);
  } else aviso('Assinatura invisível: é aplicada ao salvar.', 'ok');
}

/* ---------------------------------------------------------------- OCR */
async function dialogoOCR() {
  if (!E.paginas.length) return;
  if (!E.ocr.ok) return aviso(E.ocr.motivo || 'O OCR não está disponível neste computador.', 'erro', 8000);
  const escopo = el('select', {}, el('option', { value: 'sem', text: 'Só as páginas sem texto (escaneadas)' }), el('option', { value: 'todas', text: 'Todas as páginas' }), el('option', { value: 'atual', text: 'Só a página atual' }));
  const [lPor, cPor] = CHK('Português'); cPor.checked = true;
  const [lEng, cEng] = CHK('Inglês'); cEng.checked = true;
  const [lGirar, cGirar] = CHK('Endireitar páginas de lado ou de ponta-cabeça'); cGirar.checked = true;
  const r = await dialogo({
    titulo: 'Reconhecer texto (OCR)',
    corpo: [el('p', { class: 'dica', text: 'O texto reconhecido fica invisível por cima da imagem: dá para buscar, copiar e editar. A aparência da página não muda. Tudo roda no seu computador.' }),
      L('Páginas', escopo), el('div', { class: 'l' }, 'Idiomas do documento', el('div', { class: 'linha-props' }, lPor, lEng)), lGirar],
    botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Reconhecer', valor: 'ok', primario: true }],
    validar: () => (!cPor.checked && !cEng.checked ? 'Escolha ao menos um idioma.' : ''),
  });
  if (r !== 'ok') return;
  const idiomas = [cPor.checked && 'por', cEng.checked && 'eng'].filter(Boolean).join('+');
  const porDoc = new Map();
  const alvos = escopo.value === 'atual' ? [E.paginas[E.atual]] : E.paginas;
  for (const p of alvos) {
    if (p.doc === 'branco') continue;
    if (!porDoc.has(p.doc)) porDoc.set(p.doc, new Set());
    porDoc.get(p.doc).add(p.p);
  }
  let palavras = 0, paginas = 0, primeira = true;
  try {
    for (const [doc, ps] of porDoc) {
      const res = await ocupado(`Reconhecendo o texto${porDoc.size > 1 ? ' (' + E.docs[doc].nome + ')' : ''}…`, t => api('/api/ocr', {
        metodo: 'POST', json: { doc, idiomas, girar: cGirar.checked, paginas: escopo.value === 'sem' ? null : [...ps], tarefa: t },
      }), true);
      trocarDoc(doc, res, !primeira);
      primeira = false;
      palavras += res.resultado.palavras; paginas += res.resultado.paginas;
    }
    aviso(paginas ? `Texto reconhecido: ${palavras} palavras em ${paginas} página(s).` : 'Nenhuma página precisava de OCR (todas já têm texto).', 'ok', 6000);
  } catch (e) { erro(e); }
}

/* ---------------------------------------------------------------- marca d'água e numeração */
function seletorPaginas(cfg) {
  const s = el('select', {}, el('option', { value: 'todas', text: 'Todas as páginas' }), el('option', { value: 'intervalo', text: 'Só algumas páginas…' }));
  const iv = el('input', { type: 'text', placeholder: 'Ex.: 1-3, 5, 8-10' });
  if (cfg && cfg.paginas) { s.value = 'intervalo'; iv.value = indicesParaTexto(cfg.paginas); }
  iv.hidden = s.value !== 'intervalo';
  s.addEventListener('change', () => { iv.hidden = s.value !== 'intervalo'; });
  return {
    nos: [L('Aplicar em', s), iv],
    ler: () => {
      if (s.value !== 'intervalo') return { ok: true, paginas: null };
      const g = lerIntervalos(iv.value, E.paginas.length);
      return g && g.length ? { ok: true, paginas: g.flat() } : { ok: false };
    },
  };
}
function indicesParaTexto(lista) {
  const s = [...lista].sort((a, b) => a - b), partes = [];
  for (let i = 0; i < s.length; i++) {
    let j = i;
    while (j + 1 < s.length && s[j + 1] === s[j] + 1) j++;
    partes.push(i === j ? `${s[i] + 1}` : `${s[i] + 1}-${s[j] + 1}`);
    i = j;
  }
  return partes.join(', ');
}

async function dialogoMarca() {
  const m = E.decor.marca || {};
  const texto = el('input', { type: 'text', value: m.texto || 'CONFIDENCIAL', maxlength: 120 });
  const tam = el('input', { type: 'number', min: 8, max: 300, value: m.tamanho || 60 });
  const ang = el('select', {}, ...[[45, 'Diagonal'], [0, 'Horizontal'], [90, 'Vertical']].map(([v, t]) => el('option', { value: v, text: t })));
  ang.value = String(m.angulo ?? 45);
  const op = el('input', { type: 'range', min: 0.05, max: 1, step: 0.05, value: m.opacidade ?? 0.2 });
  let cor = m.cor || '#cc1a1a';
  const cores = el('div');
  const pintar = () => cores.replaceChildren(controleCor(cor, c => { cor = c || '#cc1a1a'; pintar(); previa(); }, ['#cc1a1a', '#111111', '#7a7974', '#2a78d6', '#1baf7a']));
  pintar();
  const sel = seletorPaginas(m);
  const antes = JSON.stringify(E.decor);
  const previa = () => {
    E.decor = { ...E.decor, marca: { texto: texto.value, tamanho: +tam.value || 60, angulo: +ang.value, opacidade: +op.value, cor, negrito: true, paginas: sel.ler().paginas || null } };
    E.paginas.forEach(p => atualizarPagina(p.uid));
  };
  [texto, tam, ang, op].forEach(i => i.addEventListener('input', previa));
  previa();
  const r = await dialogo({
    titulo: "Marca d'água",
    corpo: [L('Texto', texto), el('div', { class: 'grade2' }, L('Tamanho', tam), L('Direção', ang)), L('Transparência', op), L('Cor', cores), ...sel.nos],
    botoes: [...(m.texto ? [{ texto: 'Remover', valor: 'remover', perigo: true }] : []), { texto: 'Cancelar', valor: '' }, { texto: 'Aplicar', valor: 'ok', primario: true }],
    validar: v => (v === 'ok' && !sel.ler().ok ? 'Páginas inválidas.' : ''),
  });
  const novo = JSON.parse(antes);
  if (r === 'ok' || r === 'remover') {
    const atual = E.decor.marca;
    E.decor = novo;
    registrar();
    if (r === 'ok') E.decor.marca = { ...atual, paginas: sel.ler().paginas };
    else delete E.decor.marca;
  } else E.decor = novo;
  E.paginas.forEach(p => atualizarPagina(p.uid));
}

async function dialogoNumeracao() {
  const n = E.decor.numeracao || null, cab = E.decor.cabecalho || {}, rod = E.decor.rodape || {};
  const [lAtivo, cAtivo] = CHK('Numerar as páginas');
  cAtivo.checked = !!n || (!E.decor.cabecalho && !E.decor.rodape);
  const fmt = el('select', {}, ...['{n}', 'Página {n}', 'Página {n} de {total}', '{n} / {total}', '- {n} -'].map(v => el('option', { value: v, text: v.replace('{n}', '3').replace('{total}', '10') })));
  fmt.value = (n && n.formato) || 'Página {n} de {total}';
  const pos = el('select', {}, ...[['inf-centro', 'Embaixo, no centro'], ['inf-dir', 'Embaixo, à direita'], ['inf-esq', 'Embaixo, à esquerda'], ['sup-centro', 'Em cima, no centro'], ['sup-dir', 'Em cima, à direita'], ['sup-esq', 'Em cima, à esquerda']].map(([v, t]) => el('option', { value: v, text: t })));
  pos.value = (n && n.posicao) || 'inf-dir';
  const ini = el('input', { type: 'number', min: 0, max: 99999, value: (n && n.inicio) || 1 });
  const tam = el('input', { type: 'number', min: 5, max: 40, value: (n && n.tamanho) || 10 });
  const [lPular, cPular] = CHK('Não numerar a primeira página (capa)');
  cPular.checked = !!(n && n.paginas && !n.paginas.includes(0) && n.paginas.length === E.paginas.length - 1);
  const campo = (v, ph) => el('input', { type: 'text', value: v || '', placeholder: ph, maxlength: 200 });
  const ce = campo(cab.esq, 'Esquerda'), cc = campo(cab.centro, 'Centro'), cd = campo(cab.dir, 'Direita');
  const re = campo(rod.esq, 'Esquerda'), rc = campo(rod.centro, 'Centro'), rd = campo(rod.dir, 'Direita');
  const antes = JSON.stringify(E.decor);
  const montar = () => {
    const d = { ...E.decor };
    if (cAtivo.checked) {
      const todas = E.paginas.map((_, i) => i);
      d.numeracao = { formato: fmt.value, posicao: pos.value, inicio: +ini.value || 1, tamanho: +tam.value || 10, paginas: cPular.checked ? todas.slice(1) : null };
      if (cPular.checked) d.numeracao.inicio = (+ini.value || 1) - 1;
    } else delete d.numeracao;
    const cfgL = (a, b, c) => (a.value || b.value || c.value) ? { esq: a.value, centro: b.value, dir: c.value, tamanho: 9 } : null;
    const c1 = cfgL(ce, cc, cd), c2 = cfgL(re, rc, rd);
    if (c1) d.cabecalho = c1; else delete d.cabecalho;
    if (c2) d.rodape = c2; else delete d.rodape;
    return d;
  };
  const previa = () => { E.decor = montar(); E.paginas.forEach(p => atualizarPagina(p.uid)); };
  [cAtivo, fmt, pos, ini, tam, cPular, ce, cc, cd, re, rc, rd].forEach(i => i.addEventListener('input', previa));
  previa();
  const r = await dialogo({
    titulo: 'Numeração, cabeçalho e rodapé', largura: 600,
    corpo: [lAtivo, el('div', { class: 'grade2' }, L('Formato', fmt), L('Posição', pos), L('Começar em', ini), L('Tamanho da letra', tam)), lPular,
      el('h4', { text: 'Cabeçalho', style: 'margin:8px 0 6px' }), el('div', { class: 'grade3' }, ce, cc, cd),
      el('h4', { text: 'Rodapé', style: 'margin:14px 0 6px' }), el('div', { class: 'grade3' }, re, rc, rd),
      el('p', { class: 'muted small', style: 'margin-top:10px', text: 'Nos textos, use {n} para o número da página, {total} para o total, {data} para a data de hoje e {arquivo} para o nome do arquivo.' })],
    botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Aplicar', valor: 'ok', primario: true }],
  });
  const final = montar();
  E.decor = JSON.parse(antes);
  if (r === 'ok') { registrar(); E.decor = final; }
  E.paginas.forEach(p => atualizarPagina(p.uid));
}

/* ---------------------------------------------------------------- dividir e exportar */
async function dialogoDividir() {
  const total = E.paginas.length;
  const modo = el('select', {}, el('option', { value: 'n', text: 'A cada N páginas' }), el('option', { value: 'intervalos', text: 'Por intervalos' }), el('option', { value: 'uma', text: 'Uma página por arquivo' }));
  const n = el('input', { type: 'number', min: 1, max: total, value: Math.max(1, Math.ceil(total / 2)) });
  const iv = el('input', { type: 'text', placeholder: `Ex.: 1-3, 4-${Math.max(4, total)}` });
  const ln = L('Páginas por arquivo', n), liv = L('Intervalos (cada um vira um arquivo)', iv);
  const ajustar = () => { ln.hidden = modo.value !== 'n'; liv.hidden = modo.value !== 'intervalos'; };
  modo.addEventListener('change', ajustar);
  ajustar();
  let grupos = null;
  const calcular = () => {
    if (modo.value === 'uma') return E.paginas.map((_, i) => [i]);
    if (modo.value === 'n') {
      const k = Math.max(1, +n.value || 1), g = [];
      for (let i = 0; i < total; i += k) g.push([...Array(Math.min(k, total - i)).keys()].map(j => i + j));
      return g;
    }
    return lerIntervalos(iv.value, total);
  };
  const r = await dialogo({
    titulo: 'Dividir em vários PDFs',
    corpo: [el('p', { class: 'muted', text: `O documento tem ${total} página(s). As partes saem num arquivo .zip, com as anotações aplicadas.` }), L('Como dividir', modo), ln, liv],
    botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Dividir', valor: 'ok', primario: true }],
    validar: () => { grupos = calcular(); return grupos && grupos.length ? '' : 'Intervalos inválidos.'; },
  });
  if (r !== 'ok') return;
  try {
    const blob = await ocupado('Dividindo…', t => api('/api/exportar', { metodo: 'POST', json: { tipo: 'dividir', grupos, nome: nomeBase(E.nome), projeto: montarProjeto(), tarefa: t }, tipo: 'blob' }), true);
    if (await salvarArquivo(blob, nomeBase(E.nome) + ' - partes.zip', 'zip')) aviso(`${grupos.length} arquivo(s) gerado(s).`, 'ok');
  } catch (e) { erro(e); }
}

async function dialogoImagens() {
  const fmt = el('select', {}, el('option', { value: 'png', text: 'PNG (melhor para texto)' }), el('option', { value: 'jpeg', text: 'JPG (menor, bom para fotos)' }));
  const dpi = el('select', {}, ...[[72, 'Tela (72 dpi)'], [150, 'Normal (150 dpi)'], [300, 'Impressão (300 dpi)']].map(([v, t]) => el('option', { value: v, text: t })));
  dpi.value = '150';
  const r = await dialogo({ titulo: 'Exportar como imagens', corpo: [L('Formato', fmt), L('Resolução', dpi)], botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Exportar', valor: 'ok', primario: true }] });
  if (r !== 'ok') return;
  try {
    const blob = await ocupado('Gerando as imagens…', t => api('/api/exportar', { metodo: 'POST', json: { tipo: 'imagens', formato: fmt.value, dpi: +dpi.value, nome: nomeBase(E.nome), projeto: montarProjeto(), tarefa: t }, tipo: 'blob' }), true);
    await salvarArquivo(blob, nomeBase(E.nome) + ' - imagens.zip', 'zip');
  } catch (e) { erro(e); }
}

async function exportarTexto() {
  const docs = [...new Set(E.paginas.map(p => p.doc))].filter(d => d !== 'branco');
  try {
    const partes = [];
    for (const d of docs) partes.push(await api('/api/exportar', { metodo: 'POST', json: { tipo: 'texto', doc: d }, tipo: 'texto' }));
    await salvarArquivo(new Blob([partes.join('\n\n')], { type: 'text/plain;charset=utf-8' }), nomeBase(E.nome) + '.txt', 'txt');
  } catch (e) { erro(e); }
}

/* ---------------------------------------------------------------- senha de PDF */
async function pedirSenha(nome, errada) {
  const s = el('input', { type: 'password', autocomplete: 'off', required: true });
  const r = await dialogo({
    titulo: 'PDF protegido',
    corpo: [el('p', { text: `${errada ? 'Senha incorreta. ' : ''}"${nome}" tem senha. Digite a senha para abrir. Ela só é usada para abrir o arquivo e não fica salva.` }), L('Senha', s)],
    botoes: [{ texto: 'Pular', valor: '' }, { texto: 'Abrir', valor: 'ok', primario: true }],
    aoAbrir: () => setTimeout(() => s.focus(), 30),
  });
  return r === 'ok' ? s.value : null;
}

/* ---------------------------------------------------------------- detalhes e assinaturas */
function renderInfo() {
  const box = $('#abaInfo');
  const docs = [...new Set(E.paginas.map(p => p.doc))].map(d => E.docs[d]).filter(Boolean);
  const blocos = [];
  for (const d of docs) {
    const nPags = E.paginas.filter(p => p.doc === d.id).length;
    const b = el('div', { class: 'info-bloco' }, el('h4', { text: d.nome }),
      el('div', { text: `${d.paginas.length} página(s) no original; ${nPags} no documento atual` }),
      d.titulo ? el('div', { class: 'muted', text: `Título: ${d.titulo}` }) : '',
      el('div', { class: 'muted', text: d.tem_texto ? 'Tem texto pesquisável' : 'Sem texto (escaneado?)' }),
      d.campos && d.campos.length ? el('div', { class: 'muted', text: `Formulário com ${d.campos.length} campo(s)` }) : '');
    if (d.assinaturas && d.assinaturas.length) {
      b.append(el('h4', { text: 'Assinaturas digitais', style: 'margin-top:10px' }));
      for (const a of d.assinaturas) {
        b.append(el('div', { class: 'cert-info' },
          el('b', { text: a.assinante || a.nome || 'Assinante desconhecido' }), a.documento_assinante ? el('div', { text: a.documento_assinante }) : '',
          a.data ? el('div', { class: 'muted', text: `Assinado em ${a.data}` }) : '',
          a.motivo ? el('div', { class: 'muted', text: `Motivo: ${a.motivo}` }) : '',
          a.emissor ? el('div', { class: 'muted', text: `Emissor: ${String(a.emissor).replace(/^.*?CN=([^,]+).*$/, '$1')}` }) : '',
          el('div', { style: 'margin-top:4px;display:flex;gap:4px;flex-wrap:wrap' },
            el('span', { class: 'selo ' + (a.integra ? 'ok' : 'ruim'), text: a.integra ? 'Íntegra: o conteúdo assinado não mudou' : 'Inválida ou alterada' }),
            a.icp_brasil ? el('span', { class: 'selo ok', text: 'ICP-Brasil' }) : '',
            a.integra && !a.documento_todo ? el('span', { class: 'selo', text: 'Houve mudanças depois desta assinatura' }) : '')));
      }
      b.append(el('p', { class: 'muted small', text: 'A conferência é feita no seu computador, sem internet: confirma a integridade e quem assinou. A situação do certificado na autoridade certificadora (revogação) não é consultada.' }));
    }
    blocos.push(b);
  }
  box.replaceChildren(...(blocos.length ? blocos : [el('p', { class: 'muted', text: 'Nenhum documento aberto.' })]));
}

/* ---------------------------------------------------------------- comparar */
async function dialogoComparar(docB = null) {
  const docs = Object.values(E.docs).filter(d => E.paginas.some(p => p.doc === d.id) || d.paraComparar);
  const atual = E.paginas[E.atual] ? E.paginas[E.atual].doc : null;
  const opcoes = sel => {
    const s = el('select', {}, ...docs.map(d => el('option', { value: d.id, text: d.nome })), el('option', { value: '__novo', text: 'Abrir outro arquivo…' }));
    if (sel) s.value = sel;
    return s;
  };
  const a = opcoes(atual && atual !== 'branco' ? atual : (docs[0] && docs[0].id));
  const outros = docs.filter(d => d.id !== a.value);
  const b = opcoes(docB || (outros[0] ? outros[0].id : '__novo'));
  const r = await dialogo({
    titulo: 'Comparar PDFs', corpo: [el('p', { class: 'muted', text: 'Mostra o texto que entrou, saiu ou mudou, e as diferenças visuais página a página.' }), L('Versão anterior', a), L('Versão nova', b)],
    botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Comparar', valor: 'ok', primario: true }],
  });
  if (r !== 'ok') return;
  let ida = a.value, idb = b.value;
  if (ida === '__novo' || idb === '__novo') {
    const novo = await escolherUmArquivo();
    if (!novo) return;
    novo.paraComparar = true;
    if (ida === '__novo') ida = novo.id; else idb = novo.id;
  }
  if (ida === idb) return aviso('Escolha dois documentos diferentes.', 'erro');
  try {
    const res = await ocupado('Comparando…', () => api('/api/comparar', { metodo: 'POST', json: { a: ida, b: idb } }));
    mostrarComparacao(E.docs[ida], E.docs[idb], res);
  } catch (e) { erro(e); }
}

function mostrarComparacao(da, db, res) {
  const box = $('#comparacao');
  const largura = Math.max(280, (window.innerWidth - 340) / 2 - 40);
  const coluna = (d, lado) => {
    const col = el('div', { class: 'comp-col' }, el('h3', { text: (lado === 'a' ? 'Anterior: ' : 'Nova: ') + d.nome }));
    d.paginas.forEach((pg, i) => {
      const esc = largura / pg.w;
      const div = el('div', { class: 'comp-pg', 'data-p': i, style: `width:${pg.w * esc}px;height:${pg.h * esc}px` }, el('img', { src: `/api/pagina?doc=${d.id}&p=${i}&escala=${Math.min(2.5, esc * (window.devicePixelRatio || 1)).toFixed(2)}`, alt: '', loading: 'lazy' }));
      for (const m of res.mudancas) for (const rr of (lado === 'a' ? m.rects_a : m.rects_b)) {
        if (rr.p !== i) continue;
        div.append(el('i', { class: lado === 'a' ? 'rem' : 'add', style: `left:${rr.x * esc}px;top:${rr.y * esc}px;width:${rr.w * esc}px;height:${rr.h * esc}px` }));
      }
      if (lado === 'b') {
        const v = res.visual.find(x => x.p === i);
        if (v && v.diferenca > 0.05 && !res.mudancas.some(m => m.rects_b.some(r => r.p === i) || m.rects_a.some(r => r.p === i))) {
          for (const rr of v.regioes) div.append(el('i', { class: 'vis', style: `left:${rr.x * esc}px;top:${rr.y * esc}px;width:${rr.w * esc}px;height:${rr.h * esc}px` }));
        }
      }
      col.append(div);
    });
    return col;
  };
  const colA = coluna(da, 'a'), colB = coluna(db, 'b');
  const lista = el('ol');
  for (const m of res.mudancas) {
    lista.append(el('li', {
      onclick: () => {
        const ra = m.rects_a[0], rb = m.rects_b[0];
        const ir = (col, p, r) => { const d = col.querySelector(`.comp-pg[data-p="${p}"]`); if (d) col.scrollTo({ top: d.offsetTop + (r ? r.y * d.clientWidth / (col === colA ? da : db).paginas[p].w : 0) - 120, behavior: 'smooth' }); };
        ir(colA, ra ? ra.p : m.pa, ra);
        ir(colB, rb ? rb.p : m.pb, rb);
      },
    }, el('div', { class: 'muted small', text: `${m.tipo === 'alterado' ? 'Alterado' : m.tipo === 'removido' ? 'Removido' : 'Adicionado'} · pág. ${(m.tipo === 'adicionado' ? m.pb : m.pa) + 1}` }),
    m.antes ? el('del', { text: m.antes }) : '', m.antes && m.depois ? ' ' : '', m.depois ? el('ins', { text: m.depois }) : ''));
  }
  const difVisuais = res.visual.filter(v => v.diferenca > 0.05).length;
  const resumo = el('p', { class: 'muted', text: `${res.mudancas.length} mudança(s) no texto · ${res.semelhanca}% do texto igual · ${difVisuais} página(s) com diferença visual` + (res.paginas_a !== res.paginas_b ? ` · ${res.paginas_a} página(s) antes e ${res.paginas_b} depois` : '') });
  box.replaceChildren(
    el('div', { class: 'comp-cab' }, icone('comparar'), el('h2', { text: 'Comparação' }), el('span', { class: 'muted small', text: 'Vermelho: saiu · Verde: entrou · Tracejado: diferença visual' }),
      el('button', { class: 'btn', style: 'margin-left:auto', onclick: () => { box.hidden = true; box.replaceChildren(); }, text: 'Fechar' })),
    el('div', { class: 'comp-corpo' }, colA, colB, el('div', { class: 'comp-lista' }, resumo, res.mudancas.length ? lista : el('p', { text: 'O texto é igual nos dois.' }))));
  box.hidden = false;
}
