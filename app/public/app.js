/* Bravo PDF: início, abrir arquivos, busca, atalhos de teclado e menus. */
'use strict';

/* ---------------------------------------------------------------- preferências */
async function salvarPrefs() {
  try { await api('/api/preferencias', { metodo: 'PUT', json: E.prefs }); } catch (e) { erro(e); }
}
function aplicarTema() {
  const t = E.prefs.tema;
  if (t === 'claro') document.documentElement.dataset.theme = 'light';
  else if (t === 'escuro') document.documentElement.dataset.theme = 'dark';
  else delete document.documentElement.dataset.theme;
}

/* ---------------------------------------------------------------- abrir arquivos */
let modoAbrir = 'abrir';
function abrirSeletor(modo = 'abrir') {
  modoAbrir = modo;
  const i = $('#arquivo');
  i.value = '';
  i.click();
}

async function enviarArquivo(f) {
  let senha = null, errada = false;
  for (;;) {
    try {
      const cab = { 'X-Nome': encodeURIComponent(f.name || 'documento.pdf') };
      if (senha) cab['X-Senha'] = encodeURIComponent(senha);
      return await api('/api/abrir', { metodo: 'POST', corpo: f, cabecalhos: cab });
    } catch (e) {
      if (e.status === 401 && e.dados.senha) {
        senha = await pedirSenha(f.name, errada);
        errada = true;
        if (senha === null) return null;
        continue;
      }
      throw e;
    }
  }
}

function paginasDoDoc(d) {
  return d.paginas.map((_, i) => ({ uid: uid('p'), doc: d.id, p: i, rot: 0, itens: [] }));
}

async function abrirArquivos(arquivos, modo = 'abrir') {
  arquivos = [...arquivos].filter(Boolean);
  if (!arquivos.length) return;
  if (modo === 'abrir' && E.paginas.length) {
    const r = await dialogo({
      titulo: 'Abrir arquivos', corpo: [el('p', { text: 'Já há um documento aberto. O que fazer com os arquivos novos?' })],
      botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Fechar o atual e abrir', valor: 'trocar' }, { texto: 'Juntar ao final', valor: 'juntar', primario: true }],
    });
    if (!r) return;
    if (r === 'trocar') { if (!(await fecharTudo())) return; } else modo = 'juntar';
  }
  const novos = [];
  try {
    await ocupado(arquivos.length > 1 ? `Abrindo ${arquivos.length} arquivos…` : 'Abrindo…', async () => {
      for (const f of arquivos) {
        try {
          const d = await enviarArquivo(f);
          if (d) { E.docs[d.id] = d; novos.push(d); }
        } catch (e) { erro(new Error(`${f.name}: ${e.message}`)); }
      }
    });
  } catch (e) { erro(e); }
  if (novos.length) adicionarDocs(novos, modo);
}

function adicionarDocs(novos, modo) {
  const vazio = !E.paginas.length;
  if (!vazio) registrar();
  const pgs = novos.flatMap(paginasDoDoc);
  let pos = E.paginas.length;
  if (modo === 'inserir' && !vazio) pos = E.atual + 1;
  E.paginas.splice(pos, 0, ...pgs);
  if (vazio) {
    E.nome = novos.length > 1 ? 'Documentos juntados.pdf' : novos[0].nome.replace(/\.[^.]+$/, '') + '.pdf';
    E.hist = []; E.fut = []; E.salvoEm = 0;
  }
  mostrarTrabalho();
  renderTudo();
  if (!vazio) irPara(pos);
  const comp = novos.some(d => d.campos && d.campos.length);
  if (vazio && comp) aviso('Este PDF tem formulário: clique nos campos destacados para preencher.', '', 6000);
  if (vazio && E.acaoInicial) { const a = E.acaoInicial; E.acaoInicial = null; setTimeout(a, 200); }
}

async function escolherUmArquivo() {
  return new Promise(resolve => {
    const i = el('input', { type: 'file', accept: 'application/pdf,.pdf' });
    i.addEventListener('change', async () => {
      const f = i.files[0];
      if (!f) return resolve(null);
      try {
        const d = await ocupado('Abrindo…', () => enviarArquivo(f));
        if (d) E.docs[d.id] = d;
        resolve(d);
      } catch (e) { erro(e); resolve(null); }
    });
    i.click();
  });
}

function mostrarTrabalho() {
  const tem = E.paginas.length > 0;
  $('#inicio').hidden = tem;
  $('#trabalho').hidden = !tem;
  $('#nomeDoc').hidden = !tem;
  $('#zoomBox').hidden = !tem;
  $('#nomeDoc').value = E.nome;
}

async function fecharTudo() {
  if (temMudancas()) {
    const r = await dialogo({ titulo: 'Fechar sem salvar?', corpo: [el('p', { text: 'As mudanças que não foram salvas vão se perder.' })], botoes: [{ texto: 'Cancelar', valor: '' }, { texto: 'Fechar sem salvar', valor: 'ok', perigo: true }] });
    if (r !== 'ok') return false;
  }
  const ids = Object.keys(E.docs);
  Object.assign(E, { docs: {}, paginas: [], campos: {}, decor: {}, nome: '', sel: new Set(), atual: 0, item: null, hist: [], fut: [], objetos: {}, acertos: [], certificado: null, salvoEm: 0 });
  for (const id of ids) api('/api/doc/' + id, { metodo: 'DELETE' }).catch(() => {});
  $('#buscaLista').replaceChildren();
  $('#buscaAcoes').hidden = true;
  mostrarTrabalho();
  renderTudo();
  return true;
}
function temMudancas() { return E.paginas.length && E.hist.length !== (E.salvoEm || 0); }

/* arquivos abertos por dois cliques / "Abrir com" enquanto o app está aberto */
async function verPendentes() {
  let lista = [];
  try { lista = await api('/api/pendentes'); } catch (_) { return; }
  for (const item of lista) {
    let d = item;
    if (item.erro) {
      if (!item.senha) { aviso(`${item.nome}: ${item.erro}`, 'erro'); continue; }
      let errada = false;
      d = null;
      for (;;) {
        const s = await pedirSenha(item.nome, errada);
        if (s === null) break;
        try { d = await api('/api/destrancar', { metodo: 'POST', json: { doc: item.pendente, senha: s } }); break; }
        catch (e) { if (e.status === 401) { errada = true; continue; } erro(e); break; }
      }
      if (!d) continue;
    }
    E.docs[d.id] = d;
    if (!E.paginas.length) { adicionarDocs([d], 'abrir'); continue; }
    const r = await dialogo({
      titulo: `Abrir "${d.nome}"`, corpo: [el('p', { text: 'Já há um documento aberto.' })],
      botoes: [{ texto: 'Juntar ao final', valor: 'juntar' }, { texto: 'Fechar o atual e abrir', valor: 'trocar', primario: true }],
    });
    if (r === 'trocar') { const salvo = E.docs[d.id]; if (await fecharTudo()) { E.docs[d.id] = salvo; adicionarDocs([salvo], 'abrir'); } }
    else if (r === 'juntar') adicionarDocs([d], 'juntar');
  }
}

/* ---------------------------------------------------------------- busca */
function mostrarAba(a) {
  $$('.abas button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.aba === a)));
  $('#abaPaginas').hidden = a !== 'paginas';
  $('#abaBusca').hidden = a !== 'busca';
  $('#abaInfo').hidden = a !== 'info';
  if (a === 'info') renderInfo();
  if (a === 'busca') setTimeout(() => $('#buscaTermo').focus(), 20);
}

async function buscar(termo) {
  termo = termo.trim();
  E.acertos = [];
  E.acertoAtual = -1;
  const lista = $('#buscaLista');
  lista.replaceChildren();
  if (!termo) { $('#buscaAcoes').hidden = true; E.paginas.forEach(p => atualizarPagina(p.uid)); return; }
  const docs = [...new Set(E.paginas.map(p => p.doc))].filter(d => d !== 'branco');
  try {
    const porDoc = {};
    for (const d of docs) porDoc[d] = await api(`/api/buscar?doc=${d}&termo=${encodeURIComponent(termo)}`);
    E.paginas.forEach((pg, i) => {
      for (const h of (porDoc[pg.doc] || []).filter(h => h.p === pg.p)) E.acertos.push({ uid: pg.uid, i, rects: h.rects, trecho: h.trecho });
    });
  } catch (e) { return erro(e); }
  const tl = termo.toLowerCase();
  E.acertos.forEach((a, k) => {
    const t = a.trecho, pos = t.toLowerCase().indexOf(tl);
    const li = el('li', { 'data-k': k }, el('b', { text: `Página ${a.i + 1}` }));
    if (pos >= 0) li.append(t.slice(0, pos), el('mark', { text: t.slice(pos, pos + termo.length) }), t.slice(pos + termo.length));
    else li.append(t);
    lista.append(li);
  });
  $('#buscaAcoes').hidden = !E.acertos.length;
  $('#buscaTotal').textContent = E.acertos.length ? `${E.acertos.length} resultado(s)` : '';
  if (!E.acertos.length) lista.append(el('li', { class: 'muted', text: docs.some(d => !E.docs[d].tem_texto) ? 'Nada encontrado. Se o documento for escaneado, use o OCR antes.' : 'Nada encontrado.' }));
  E.paginas.forEach(p => atualizarPagina(p.uid));
  if (E.acertos.length) irAcerto(0);
}
function irAcerto(k) {
  if (!E.acertos.length) return;
  k = (k + E.acertos.length) % E.acertos.length;
  const ant = E.acertos[E.acertoAtual];
  E.acertoAtual = k;
  const a = E.acertos[k];
  if (ant) atualizarPagina(ant.uid);
  atualizarPagina(a.uid);
  $$('#buscaLista li').forEach(li => li.classList.toggle('atual', +li.dataset.k === k));
  const div = $(`.pg[data-uid="${a.uid}"]`), v = $('#visor');
  if (!div) return;
  const pg = paginaPorUid(a.uid), b = dimsBase(pg), r = a.rects[0];
  let yRel = r ? r.y : 0;
  if (pg.rot === 180) yRel = b.h - yRel; else if (pg.rot === 90) yRel = r ? r.x : 0; else if (pg.rot === 270) yRel = b.w - (r ? r.x : 0);
  v.scrollTo({ top: div.offsetTop + yRel * E.zoom - v.clientHeight / 3, behavior: 'smooth' });
  E.atual = a.i;
  marcarAtual();
}
function acertosParaItens(tipo) {
  if (!E.acertos.length) return;
  registrar();
  for (const a of E.acertos) {
    const pg = paginaPorUid(a.uid);
    for (const r of a.rects) {
      const pad = tipo === 'tarja' ? 1.5 : 0.8;
      pg.itens.push({ id: uid('i'), tipo, x: r.x - pad, y: r.y - pad, w: r.w + 2 * pad, h: r.h + 2 * pad, ...(tipo === 'marca' ? E.estilo.marca : {}) });
    }
  }
  E.paginas.forEach(p => atualizarPagina(p.uid));
  aviso(tipo === 'tarja' ? `${E.acertos.length} ocorrência(s) tarjada(s). O conteúdo some de verdade quando você salvar.` : `${E.acertos.length} ocorrência(s) marcada(s).`, 'ok', 6000);
}

/* ---------------------------------------------------------------- imprimir */
async function imprimir() {
  if (!E.paginas.length) return;
  const zoomAntes = E.zoomModo;
  definirZoom(96 / 72);  // 1 ponto = 1/72 de polegada: imprime no tamanho real
  await ocupado('Preparando a impressão…', async () => {
    const imgs = [];
    $$('.pg').forEach(div => {
      const pg = paginaPorUid(div.dataset.uid);
      const img = div.querySelector('.pg-in img');
      if (!img || !pg) return;
      img.dataset.escala = '2.5';
      imgs.push(new Promise(ok => { img.onload = ok; img.onerror = ok; img.src = urlPagina(pg, 2.5); }));
    });
    await Promise.all(imgs);
  });
  if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.imprimir) window.webkit.messageHandlers.imprimir.postMessage('');
  else window.print();
  setTimeout(() => definirZoom(zoomAntes), 500);
}

/* ---------------------------------------------------------------- menus e atalhos */
async function acaoMenu(a) {
  $('#menuDoc').open = false;
  if (!E.paginas.length && !['fechar'].includes(a)) { E.acaoInicial = () => acaoMenu(a); return abrirSeletor('abrir'); }
  switch (a) {
    case 'inserir': return abrirSeletor('juntar');
    case 'dividir': return dialogoDividir();
    case 'extrair': {
      const alvos = alvosPaginas();
      if (!E.sel.size) aviso('Nenhuma página selecionada: vou extrair a página atual. Selecione nas miniaturas para escolher outras.', '', 5000);
      return dialogoSalvar({ paginas: alvos, titulo: `Extrair ${alvos.length} página(s)` });
    }
    case 'marcadagua': return dialogoMarca();
    case 'numeracao': return dialogoNumeracao();
    case 'ocr': return dialogoOCR();
    case 'certificado': return dialogoCertificado();
    case 'assinaturas': mostrarAba('info'); return;
    case 'comparar': return dialogoComparar();
    case 'comprimir': return dialogoSalvar({ comprimir: 'media', titulo: 'Comprimir e salvar' });
    case 'proteger': return dialogoSalvar({ senha: true, titulo: 'Proteger com senha' });
    case 'imagens': return dialogoImagens();
    case 'texto': return exportarTexto();
    case 'imprimir': return imprimir();
    case 'fechar': return fecharTudo();
    default:
  }
}

function atalhoInicio(a) {
  const depois = {
    editar: () => escolherFerramenta('texto'),
    assinar: () => escolherFerramenta('assinatura'),
    formulario: () => {},
    juntar: () => { aviso('Arraste as miniaturas para acertar a ordem e clique em Salvar.', '', 6000); },
    organizar: () => { mostrarAba('paginas'); aviso('Selecione páginas nas miniaturas para girar, duplicar, apagar ou arrastar.', '', 6000); },
    imagens: () => aviso('As imagens viraram páginas. Clique em Salvar para gerar o PDF.', '', 6000),
    ocr: () => dialogoOCR(),
    tarjar: () => { escolherFerramenta('tarja'); mostrarAba('busca'); aviso('Arraste sobre o que quer apagar, ou busque um termo (ex.: o CPF) e use "Tarjar todas".', '', 8000); },
    comprimir: () => dialogoSalvar({ comprimir: 'media', titulo: 'Comprimir e salvar' }),
    comparar: () => dialogoComparar(),
  }[a];
  E.acaoInicial = depois;
  const i = $('#arquivo');
  i.accept = a === 'imagens' ? 'image/*' : 'application/pdf,.pdf,image/png,image/jpeg,image/webp,image/tiff,image/gif,image/bmp';
  i.multiple = true;
  abrirSeletor('abrir');
}

const TECLAS_F = { v: 'selecionar', h: 'mao', e: 'editar', t: 'texto', m: 'marca', n: 'nota', p: 'caneta', r: 'retangulo', l: 'linha', a: 'seta', s: 'assinatura' };
function teclado(ev) {
  const alvo = ev.target;
  const digitando = alvo.closest && alvo.closest('input, textarea, select, [contenteditable]');
  const ctrl = ev.ctrlKey || ev.metaKey;
  if ($('#dlg').open) return;
  if (ctrl && ev.key.toLowerCase() === 'o') { ev.preventDefault(); return abrirSeletor('abrir'); }
  if (ctrl && ev.key.toLowerCase() === 's') { ev.preventDefault(); return dialogoSalvar(); }
  if (ctrl && ev.key.toLowerCase() === 'p') { ev.preventDefault(); return imprimir(); }
  if (ctrl && ev.key.toLowerCase() === 'f') { ev.preventDefault(); return mostrarAba('busca'); }
  if (digitando) return;
  if (ctrl && ev.key.toLowerCase() === 'z') { ev.preventDefault(); return ev.shiftKey ? refazer() : desfazer(); }
  if (ctrl && ev.key.toLowerCase() === 'y') { ev.preventDefault(); return refazer(); }
  if (ctrl && (ev.key === '+' || ev.key === '=')) { ev.preventDefault(); return passoZoom(1); }
  if (ctrl && ev.key === '-') { ev.preventDefault(); return passoZoom(-1); }
  if (ctrl && ev.key === '0') { ev.preventDefault(); return definirZoom('largura'); }
  if (ctrl && ev.key.toLowerCase() === 'd' && E.item) { ev.preventDefault(); return duplicarItem(); }
  if (!E.paginas.length) return;
  if (ev.key === 'Delete' || ev.key === 'Backspace') {
    if (E.item) { ev.preventDefault(); return apagarItem(); }
    if (E.sel.size && alvo.closest && alvo.closest('#lateral')) { ev.preventDefault(); return opPagina('apagar'); }
  }
  if (ev.key === 'Escape') {
    if (E.item) { const u = E.item.pg; E.item = null; atualizarPagina(u); renderProps(); return; }
    if (E.ferramenta !== 'selecionar') return escolherFerramenta('selecionar');
    E.sel.clear(); atualizarSelInfo();
    return;
  }
  if (E.item && ev.key.startsWith('Arrow')) {
    const s = itemSel();
    const d = ev.shiftKey ? 10 : 1;
    const [dx, dy] = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }[ev.key];
    ev.preventDefault();
    registrar();
    moverItem(s.it, JSON.parse(JSON.stringify(s.it)), dx, dy);
    atualizarPagina(s.pg.uid);
    return;
  }
  if (ev.key === 'PageDown' || (ev.key === 'ArrowRight' && E.zoomModo === 'pagina')) { ev.preventDefault(); return irPara(Math.min(E.atual + 1, E.paginas.length - 1)); }
  if (ev.key === 'PageUp' || (ev.key === 'ArrowLeft' && E.zoomModo === 'pagina')) { ev.preventDefault(); return irPara(Math.max(E.atual - 1, 0)); }
  if (ev.key === 'Home' && ctrl) return irPara(0);
  if (ev.key === 'End' && ctrl) return irPara(E.paginas.length - 1);
  if (!ctrl && !ev.altKey && TECLAS_F[ev.key.toLowerCase()]) escolherFerramenta(TECLAS_F[ev.key.toLowerCase()]);
}

/* ---------------------------------------------------------------- arrastar arquivos para a janela */
function iniciarSoltar() {
  let n = 0;
  const temArquivos = e => e.dataTransfer && [...e.dataTransfer.types].includes('Files');
  window.addEventListener('dragenter', e => { if (!temArquivos(e)) return; e.preventDefault(); n++; $('#drop').hidden = false; });
  window.addEventListener('dragleave', e => { if (!temArquivos(e)) return; n = Math.max(0, n - 1); if (!n) $('#drop').hidden = true; });
  window.addEventListener('dragover', e => { if (temArquivos(e)) e.preventDefault(); });
  window.addEventListener('drop', e => {
    if (!temArquivos(e)) return;
    e.preventDefault();
    n = 0;
    $('#drop').hidden = true;
    abrirArquivos(e.dataTransfer.files, E.paginas.length ? 'juntar' : 'abrir');
  });
}

/* ---------------------------------------------------------------- início */
async function iniciar() {
  try {
    const st = await api('/api/estado');
    E.prefs = st.preferencias || {};
    E.ocr = st.ocr || { ok: false };
    E.sistema = st.sistema;
    if (E.prefs.estilo) for (const [k, v] of Object.entries(E.prefs.estilo)) if (E.estilo[k]) Object.assign(E.estilo[k], v);
  } catch (e) { erro(e); }
  aplicarTema();
  mostrarTrabalho();

  $('#btAbrir').addEventListener('click', () => abrirSeletor('abrir'));
  $('#btAbrir2').addEventListener('click', () => abrirSeletor('abrir'));
  $('#arquivo').addEventListener('change', e => {
    const files = [...e.target.files];
    e.target.accept = 'application/pdf,.pdf,image/png,image/jpeg,image/webp,image/tiff,image/gif,image/bmp';
    abrirArquivos(files, modoAbrir);
  });
  $('#btSalvar').addEventListener('click', () => dialogoSalvar());
  $('#btDesfazer').addEventListener('click', desfazer);
  $('#btRefazer').addEventListener('click', refazer);
  $('#btMais').addEventListener('click', () => passoZoom(1));
  $('#btMenos').addEventListener('click', () => passoZoom(-1));
  $('#zoomSel').addEventListener('change', e => { const v = e.target.value; definirZoom(isNaN(+v) ? v : +v); });
  $('#btTema').addEventListener('click', () => {
    const escuro = getComputedStyle(document.documentElement).colorScheme.includes('dark');
    E.prefs.tema = escuro ? 'claro' : 'escuro';
    aplicarTema();
    salvarPrefs();
  });
  $('#nomeDoc').addEventListener('change', e => {
    let v = e.target.value.trim() || 'documento.pdf';
    if (!/\.pdf$/i.test(v)) v += '.pdf';
    E.nome = e.target.value = v;
  });
  $('#nomeDoc').addEventListener('keydown', e => { if (e.key === 'Enter') e.target.blur(); });
  $$('#menuDoc [data-acao]').forEach(b => b.addEventListener('click', () => acaoMenu(b.dataset.acao)));
  document.addEventListener('click', e => { const m = $('#menuDoc'); if (m.open && !m.contains(e.target)) m.open = false; });
  $$('[data-atalho]').forEach(b => b.addEventListener('click', () => atalhoInicio(b.dataset.atalho)));
  $$('#ferramentas [data-f]').forEach(b => b.addEventListener('click', () => escolherFerramenta(b.dataset.f)));
  $$('[data-pg]').forEach(b => b.addEventListener('click', () => opPagina(b.dataset.pg)));
  $$('.abas button').forEach(b => b.addEventListener('click', () => mostrarAba(b.dataset.aba)));
  $('#buscaForm').addEventListener('submit', e => {
    e.preventDefault();
    const t = $('#buscaTermo').value;
    if (t.trim() && E.ultimaBusca === t && E.acertos.length) irAcerto(E.acertoAtual + 1);
    else { E.ultimaBusca = t; buscar(t); }
  });
  $('#buscaLista').addEventListener('click', e => { const li = e.target.closest('li[data-k]'); if (li) irAcerto(+li.dataset.k); });
  $('#buscaMarcar').addEventListener('click', () => acertosParaItens('marca'));
  $('#buscaTarjar').addEventListener('click', () => acertosParaItens('tarja'));
  const menu = $('#menuDoc .menu-pop');
  menu.insertBefore(el('button', { 'data-acao': 'imprimir', onclick: () => acaoMenu('imprimir') }, icone('pagina'), 'Imprimir'), menu.querySelector('[data-acao="fechar"]'));

  iniciarMiniaturas();
  iniciarInteracao();
  acompanharRolagem();
  iniciarSoltar();
  document.addEventListener('keydown', teclado);
  let rz;
  window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (typeof E.zoomModo === 'string' && E.paginas.length) renderPaginas(); }, 150); });
  window.addEventListener('beforeunload', e => { if (temMudancas()) { e.preventDefault(); e.returnValue = ''; } });
  escolherFerramenta('selecionar');
  renderTudo();
  setInterval(verPendentes, 1500);
  verPendentes();
  // guarda as preferências de estilo das ferramentas de vez em quando
  let ultimoEstilo = JSON.stringify(E.estilo);
  setInterval(() => {
    const atual = JSON.stringify(E.estilo);
    if (atual !== ultimoEstilo) { ultimoEstilo = atual; E.prefs.estilo = JSON.parse(atual); salvarPrefs(); }
  }, 5000);
}

iniciar();
