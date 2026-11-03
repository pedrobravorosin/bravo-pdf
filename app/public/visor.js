/* Bravo PDF: estado do documento, páginas, miniaturas, ferramentas e anotações. */
'use strict';

const E = {
  docs: {},            // id -> {id, nome, paginas:[{w,h}], campos, assinaturas, tem_texto}
  paginas: [],         // [{uid, doc, p, rot, itens:[...], w, h (branco)}]
  campos: {},          // doc -> {nome: valor}
  decor: {},           // marca, numeracao, cabecalho, rodape
  nome: '',
  sel: new Set(), atual: 0, ancora: null,
  ferramenta: 'selecionar', zoom: 1, zoomModo: 'largura',
  item: null,          // {pg: uid, id}
  hist: [], fut: [],
  estilo: {
    marca: { cor: '#ffd400', opacidade: 0.45 },
    sublinhado: { cor: '#d03b3b', espessura: 1.5 },
    tachado: { cor: '#d03b3b', espessura: 1.5 },
    texto: { cor: '#111111', fonte: 'helv', tamanho: 14, negrito: false, italico: false, fundo: null, borda: false },
    nota: { cor: '#ffd400' },
    caneta: { cor: '#111111', espessura: 2, opacidade: 1 },
    retangulo: { cor: '#C2410C', preenchimento: null, espessura: 2, opacidade: 1 },
    elipse: { cor: '#C2410C', preenchimento: null, espessura: 2, opacidade: 1 },
    linha: { cor: '#C2410C', espessura: 2, opacidade: 1 },
    seta: { cor: '#C2410C', espessura: 2, opacidade: 1 },
    carimbo: { cor: '#C2410C', texto: 'APROVADO', tamanho: 18, fonte: 'helv' },
    corretivo: { cor: '#ffffff' },
    imagem: { opacidade: 1 },
  },
  assinaturaAtiva: null, imagemAtiva: null, certificado: null,
  prefs: {}, objetos: {}, ocr: { ok: false }, acertos: [], acertoAtual: -1,
};

const CORES = ['#111111', '#C2410C', '#d03b3b', '#ffd400', '#1baf7a', '#2a78d6', '#6250d6', '#e87ba4', '#ffffff'];
const CORES_MARCA = ['#ffd400', '#7ee081', '#7cc6ff', '#ff9ec8', '#ffb46b'];
const NOMES_F = {
  selecionar: 'Selecionar', mao: 'Mover a página', editar: 'Editar texto do PDF', texto: 'Caixa de texto',
  marca: 'Marca-texto', sublinhado: 'Sublinhar', tachado: 'Riscar', nota: 'Nota', caneta: 'Caneta',
  retangulo: 'Retângulo', elipse: 'Elipse', linha: 'Linha', seta: 'Seta', carimbo: 'Carimbo', imagem: 'Imagem',
  assinatura: 'Assinatura', certificado: 'Certificado digital', corretivo: 'Corretivo', tarja: 'Tarja definitiva',
};
const ARRASTAR_CAIXA = new Set(['marca', 'sublinhado', 'tachado', 'retangulo', 'elipse', 'corretivo', 'tarja', 'certificado']);

/* ---------------------------------------------------------------- histórico */
function instantaneo() { return JSON.stringify({ paginas: E.paginas, campos: E.campos, decor: E.decor }); }
function registrar() {
  E.hist.push(instantaneo());
  if (E.hist.length > 150) E.hist.shift();
  E.fut = [];
  atualizarBotoes();
}
function restaurar(json) {
  const d = JSON.parse(json);
  E.paginas = d.paginas; E.campos = d.campos; E.decor = d.decor;
  E.item = null;
  const uids = new Set(E.paginas.map(p => p.uid));
  E.sel = new Set([...E.sel].filter(u => uids.has(u)));
  E.atual = clamp(E.atual, 0, Math.max(0, E.paginas.length - 1));
  renderTudo();
}
function desfazer() { if (!E.hist.length) return; fecharEditores(); E.fut.push(instantaneo()); restaurar(E.hist.pop()); }
function refazer() { if (!E.fut.length) return; fecharEditores(); E.hist.push(instantaneo()); restaurar(E.fut.pop()); }

/* ---------------------------------------------------------------- medidas */
function dimsBase(pg) {
  if (pg.doc === 'branco') return { w: pg.w, h: pg.h };
  const d = E.docs[pg.doc];
  return d ? d.paginas[pg.p] : { w: 595, h: 842 };
}
function dimsTela(pg) {
  const b = dimsBase(pg);
  return pg.rot % 180 ? { w: b.h, h: b.w } : b;
}
function paginaPorUid(u) { return E.paginas.find(p => p.uid === u); }
function indicePorUid(u) { return E.paginas.findIndex(p => p.uid === u); }
function itemSel() {
  if (!E.item) return null;
  const pg = paginaPorUid(E.item.pg);
  const it = pg && pg.itens.find(i => i.id === E.item.id);
  return it ? { pg, it } : null;
}
function escalaImg() {
  const s = E.zoom * (window.devicePixelRatio || 1);
  return Math.max(0.5, Math.min(5, Math.ceil(s * 4) / 4));
}
function urlPagina(pg, escala, fmt) {
  return `/api/pagina?doc=${pg.doc}&p=${pg.p}&escala=${escala}` + (fmt ? `&fmt=${fmt}` : '');
}

/* ---------------------------------------------------------------- zoom */
function calcularZoom() {
  const v = $('#visor');
  if (!E.paginas.length) return;
  const maxW = Math.max(...E.paginas.map(p => dimsTela(p).w));
  const maxH = Math.max(...E.paginas.map(p => dimsTela(p).h));
  if (E.zoomModo === 'largura') E.zoom = clamp((v.clientWidth - 64) / maxW, 0.2, 4);
  else if (E.zoomModo === 'pagina') E.zoom = clamp(Math.min((v.clientWidth - 64) / maxW, (v.clientHeight - 60) / maxH), 0.2, 4);
}
function definirZoom(modo) {
  const v = $('#visor');
  const u = E.paginas[E.atual] && E.paginas[E.atual].uid;
  E.zoomModo = modo;
  if (typeof modo === 'number') E.zoom = clamp(modo, 0.2, 5);
  renderPaginas();
  const sel = $('#zoomSel');
  sel.value = typeof modo === 'number' ? '' : modo;
  if (typeof modo === 'number') {
    let o = $$('option', sel).find(o => +o.value === modo);
    if (!o) { $$('option[data-livre]', sel).forEach(x => x.remove()); o = el('option', { value: modo, 'data-livre': 1, text: Math.round(modo * 100) + '%' }); sel.append(o); }
    sel.value = String(modo);
  }
  if (u) irPara(indicePorUid(u), false);
  void v;
}
function passoZoom(d) {
  const niveis = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5];
  const z = E.zoom;
  const prox = d > 0 ? niveis.find(n => n > z + 0.01) : [...niveis].reverse().find(n => n < z - 0.01);
  if (prox) definirZoom(prox);
}

/* ---------------------------------------------------------------- render: páginas */
let observador;
function renderTudo() {
  renderPaginas();
  renderMiniaturas();
  renderProps();
  renderFaixas();
  atualizarBotoes();
}

function renderPaginas() {
  calcularZoom();
  const c = $('#paginas');
  const existentes = new Map($$('.pg', c).map(e => [e.dataset.uid, e]));
  if (observador) observador.disconnect();
  observador = new IntersectionObserver(ents => {
    for (const en of ents) if (en.isIntersecting) carregarImagem(en.target);
  }, { root: $('#visor'), rootMargin: '600px 0px' });
  const frag = document.createDocumentFragment();
  E.paginas.forEach((pg, i) => {
    let div = existentes.get(pg.uid);
    if (!div) div = el('div', { class: 'pg', 'data-uid': pg.uid }, el('div', { class: 'pg-in' }), el('div', { class: 'pg-num' }));
    existentes.delete(pg.uid);
    montarPagina(div, pg, i);
    frag.append(div);
    observador.observe(div);
  });
  c.replaceChildren(frag);
  marcarAtual();
}

function montarPagina(div, pg, i) {
  const z = E.zoom;
  const b = dimsBase(pg), t = dimsTela(pg);
  div.style.width = t.w * z + 'px';
  div.style.height = t.h * z + 'px';
  div.querySelector('.pg-num').textContent = `${i + 1}`;
  const inn = div.querySelector('.pg-in');
  inn.style.width = b.w * z + 'px';
  inn.style.height = b.h * z + 'px';
  inn.style.left = (t.w - b.w) * z / 2 + 'px';
  inn.style.top = (t.h - b.h) * z / 2 + 'px';
  inn.style.transform = pg.rot ? `rotate(${pg.rot}deg)` : '';
  const chave = `${pg.doc}|${pg.p}`;
  let img = inn.querySelector('img');
  if (pg.doc === 'branco') { if (img) img.remove(); img = null; }
  else if (!img) { img = el('img', { alt: '', draggable: 'false' }); inn.prepend(img); }
  if (img && img.dataset.chave !== chave) { img.removeAttribute('src'); img.dataset.chave = chave; img.dataset.escala = ''; }
  desenharCamada(div, pg);
  desenharCampos(div, pg);
  if (div.dataset.visivel === '1') carregarImagem(div);
}

function carregarImagem(div) {
  div.dataset.visivel = '1';
  const pg = paginaPorUid(div.dataset.uid);
  if (!pg || pg.doc === 'branco') return;
  const img = div.querySelector('.pg-in img');
  const s = escalaImg();
  if (img && img.dataset.escala !== String(s)) {
    img.dataset.escala = String(s);
    const novo = new Image();
    novo.onload = () => { img.src = novo.src; };
    novo.src = urlPagina(pg, s);
  }
}

function atualizarPagina(uid) {
  const div = $(`.pg[data-uid="${uid}"]`);
  const pg = paginaPorUid(uid);
  if (div && pg) desenharCamada(div, pg);
  atualizarMiniaturaMarcas(uid);
}

/* ---------------------------------------------------------------- camada de anotações (SVG) */
function desenharCamada(div, pg) {
  const inn = div.querySelector('.pg-in');
  const b = dimsBase(pg);
  let svg = inn.querySelector('svg.camada');
  if (!svg) { svg = el('svg:svg', { class: 'camada' }); inn.append(svg); }
  svg.setAttribute('viewBox', `0 0 ${b.w} ${b.h}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.replaceChildren();
  previaDecor(svg, pg, b);
  for (const it of pg.itens) {
    const g = desenharItem(it);
    if (g) { g.dataset.item = it.id; g.classList.add('item'); svg.append(g); }
  }
  if (E.certificado && E.certificado.caixa && E.certificado.caixa.pg === pg.uid) {
    const c = E.certificado.caixa;
    svg.append(el('svg:rect', { class: 'cert-caixa', x: c.x, y: c.y, width: c.w, height: c.h, 'stroke-dasharray': '4 3', 'stroke-width': 1 }),
      el('svg:text', { x: c.x + 6, y: c.y + Math.min(14, c.h - 4), 'font-size': Math.min(11, c.h * 0.4), class: 'cert-texto', 'font-family': FAMILIAS.helv, text: 'Assinatura digital' }));
  }
  // acertos da busca
  E.acertos.forEach((a, k) => {
    if (a.uid !== pg.uid) return;
    for (const r of a.rects) svg.append(el('svg:rect', { class: 'acerto' + (k === E.acertoAtual ? ' atual' : ''), x: r.x - 1, y: r.y - 1, width: r.w + 2, height: r.h + 2 }));
  });
  // blocos de texto editáveis
  if (E.ferramenta === 'editar') {
    const objs = E.objetos[`${pg.doc}|${pg.p}`];
    if (objs) for (const o of objs) svg.append(el('svg:rect', { class: 'obj-texto', x: o.x - 1, y: o.y - 1, width: o.w + 2, height: o.h + 2, 'data-obj': o.id }));
    else if (pg.doc !== 'branco') carregarObjetos(pg);
  }
  // seleção
  const s = itemSel();
  if (s && s.pg.uid === pg.uid) {
    const bb = caixaItem(s.it);
    svg.append(el('svg:rect', { class: 'sel-caixa', x: bb.x - 2, y: bb.y - 2, width: bb.w + 4, height: bb.h + 4 }));
    const r = 5 / E.zoom;
    if (s.it.tipo === 'linha' || s.it.tipo === 'seta') {
      s.it.pontos.forEach((p, k) => svg.append(el('svg:circle', { class: 'alca', cx: p[0], cy: p[1], r, 'data-alca': 'p' + k })));
    } else if (s.it.tipo !== 'nota') {
      svg.append(el('svg:rect', { class: 'alca', x: bb.x + bb.w - r, y: bb.y + bb.h - r, width: 2 * r, height: 2 * r, 'data-alca': 'canto' }));
    }
  }
}

function caixaItem(it) {
  if (it.tipo === 'linha' || it.tipo === 'seta') {
    const [[a, b], [c, d]] = it.pontos;
    return { x: Math.min(a, c), y: Math.min(b, d), w: Math.abs(c - a), h: Math.abs(d - b) };
  }
  if (it.tipo === 'caneta') {
    const xs = it.tracos.flat().map(p => p[0]), ys = it.tracos.flat().map(p => p[1]);
    const x = Math.min(...xs), y = Math.min(...ys);
    return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
  }
  if (it.tipo === 'nota') return { x: it.x, y: it.y, w: 20, h: 20 };
  return { x: it.x, y: it.y, w: it.w, h: it.h };
}

function setaPontas(p0, p1, esp) {
  const ang = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]);
  const t = Math.max(8, esp * 4);
  return [[p1[0] - t * Math.cos(ang - 0.45), p1[1] - t * Math.sin(ang - 0.45)], p1,
    [p1[0] - t * Math.cos(ang + 0.45), p1[1] - t * Math.sin(ang + 0.45)]];
}

function desenharItem(it) {
  const g = el('svg:g');
  const op = it.opacidade ?? 1;
  const alvo = (x, y, w, h) => el('svg:rect', { x, y, width: Math.max(w, 4), height: Math.max(h, 4), fill: 'transparent' });
  switch (it.tipo) {
    case 'marca':
      g.append(el('svg:rect', { x: it.x, y: it.y, width: it.w, height: it.h, fill: it.cor, 'fill-opacity': it.opacidade ?? 0.45, style: 'mix-blend-mode:multiply' }));
      break;
    case 'sublinhado': case 'tachado': {
      const yy = it.tipo === 'sublinhado' ? it.y + it.h - it.espessura / 2 : it.y + it.h * 0.55;
      g.append(alvo(it.x, it.y, it.w, it.h), el('svg:line', { x1: it.x, y1: yy, x2: it.x + it.w, y2: yy, stroke: it.cor, 'stroke-width': it.espessura }));
      break;
    }
    case 'retangulo': case 'elipse': {
      const comum = { stroke: it.cor, 'stroke-width': it.espessura, fill: it.preenchimento || 'transparent', opacity: op };
      g.append(it.tipo === 'elipse'
        ? el('svg:ellipse', { cx: it.x + it.w / 2, cy: it.y + it.h / 2, rx: it.w / 2, ry: it.h / 2, ...comum })
        : el('svg:rect', { x: it.x, y: it.y, width: it.w, height: it.h, ...comum }));
      break;
    }
    case 'corretivo':
      g.append(el('svg:rect', { x: it.x, y: it.y, width: it.w, height: it.h, fill: it.cor || '#fff' }));
      break;
    case 'tarja':
      g.append(el('svg:rect', { x: it.x, y: it.y, width: it.w, height: it.h, fill: '#000', 'fill-opacity': 0.82, stroke: '#d03b3b', 'stroke-width': 1, 'stroke-dasharray': '3 2' }));
      if (it.h > 9 && it.w > 40) g.append(el('svg:text', { x: it.x + 3, y: it.y + Math.min(it.h - 3, 10), 'font-size': Math.min(8, it.h - 3), fill: '#ff8a8a', 'font-family': FAMILIAS.helv, text: 'tarja' }));
      break;
    case 'linha': case 'seta': {
      const [p0, p1] = it.pontos;
      g.setAttribute('opacity', op);
      g.append(el('svg:line', { x1: p0[0], y1: p0[1], x2: p1[0], y2: p1[1], stroke: 'transparent', 'stroke-width': Math.max(10, it.espessura + 8) }),
        el('svg:line', { x1: p0[0], y1: p0[1], x2: p1[0], y2: p1[1], stroke: it.cor, 'stroke-width': it.espessura, 'stroke-linecap': 'round' }));
      if (it.tipo === 'seta') g.append(el('svg:polyline', { points: setaPontas(p0, p1, it.espessura).map(p => p.join(',')).join(' '), stroke: it.cor, 'stroke-width': it.espessura, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
      break;
    }
    case 'caneta':
      g.setAttribute('opacity', op);
      for (const t of it.tracos) {
        g.append(el('svg:polyline', { points: t.map(p => p.join(',')).join(' '), stroke: 'transparent', 'stroke-width': it.espessura + 8, fill: 'none' }),
          el('svg:polyline', { points: t.map(p => p.join(',')).join(' '), stroke: it.cor, 'stroke-width': it.espessura, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
      }
      break;
    case 'texto': case 'carimbo': {
      const pad = it.tipo === 'carimbo' ? 4 : 2;
      if (it.tipo === 'carimbo') g.append(el('svg:rect', { x: it.x + 1, y: it.y + 1, width: it.w - 2, height: it.h - 2, rx: 2, fill: 'transparent', stroke: it.cor, 'stroke-width': 2 }));
      else g.append(el('svg:rect', { x: it.x, y: it.y, width: it.w, height: it.h, fill: it.fundo || 'transparent', stroke: it.borda ? it.cor : 'transparent', 'stroke-width': 1 }));
      const linhas = it.linhas || [it.texto || ''];
      linhas.forEach((ln, k) => {
        g.append(el('svg:text', {
          x: it.x + pad, y: it.y + pad + it.tamanho * (0.94 + 1.2 * k), fill: it.cor, 'font-size': it.tamanho,
          'font-family': FAMILIAS[it.fonte] || FAMILIAS.helv, 'font-weight': (it.negrito || it.tipo === 'carimbo') ? 'bold' : 'normal',
          'font-style': it.italico ? 'italic' : 'normal', 'xml:space': 'preserve', text: ln,
        }));
      });
      if (it.tipo === 'texto' && !linhas.join('').trim()) g.append(el('svg:rect', { x: it.x, y: it.y, width: it.w, height: it.h, fill: 'none', stroke: '#999', 'stroke-dasharray': '2 2', 'stroke-width': 0.6 }));
      break;
    }
    case 'nota':
      g.append(el('svg:rect', { x: it.x + 1, y: it.y + 1, width: 18, height: 15, fill: it.cor, stroke: '#594d1a', 'stroke-width': 1 }),
        el('svg:path', { d: `M${it.x + 5} ${it.y + 16}l0 4 5-4z`, fill: it.cor, stroke: '#594d1a', 'stroke-width': 1 }),
        el('svg:path', { d: `M${it.x + 4} ${it.y + 5.5}h12M${it.x + 4} ${it.y + 9}h12M${it.x + 4} ${it.y + 12.5}h8`, stroke: '#594d1a', 'stroke-width': 1 }));
      if (it.texto) g.append(el('svg:title', { text: it.texto }));
      break;
    case 'imagem': case 'assinatura':
      g.append(el('svg:image', { href: it.imagem, x: it.x, y: it.y, width: it.w, height: it.h, preserveAspectRatio: 'none', opacity: op }));
      break;
    default:
      return null;
  }
  return g;
}

function previaDecor(svg, pg, b) {
  const D = E.decor;
  const idx = indicePorUid(pg.uid), total = E.paginas.length;
  const alvo = c => !c.paginas || c.paginas.includes(idx);
  // a prévia é desenhada na orientação final (com a rotação da página)
  const t = pg.rot % 180 ? { w: b.h, h: b.w } : b;
  const g = el('svg:g', { transform: `rotate(${-pg.rot} ${b.w / 2} ${b.h / 2}) translate(${(b.w - t.w) / 2} ${(b.h - t.h) / 2})`, 'pointer-events': 'none' });
  let algum = false;
  if (D.marca && D.marca.texto && alvo(D.marca)) {
    const m = D.marca;
    let tam = +m.tamanho || 60;
    const fonte = { fonte: m.fonte || 'helv', negrito: m.negrito !== false, tamanho: tam };
    let larg = larguraTexto(m.texto, fonte);
    const ang = +m.angulo || 0;
    const caber = ang % 180 ? Math.hypot(t.w, t.h) * 0.8 : t.w * 0.9;
    if (larg > caber) { tam *= caber / larg; larg = caber; }
    g.append(el('svg:text', {
      x: t.w / 2, y: t.h / 2, 'text-anchor': 'middle', 'dominant-baseline': 'central', 'font-size': tam,
      'font-family': FAMILIAS[m.fonte] || FAMILIAS.helv, 'font-weight': m.negrito === false ? 'normal' : 'bold',
      fill: m.cor || '#cc1a1a', 'fill-opacity': m.opacidade ?? 0.2, transform: `rotate(${-ang} ${t.w / 2} ${t.h / 2})`, text: m.texto,
    }));
    algum = true;
  }
  const linha = (txt, onde, cfg, padrao) => {
    const tam = +cfg.tamanho || padrao, margem = +cfg.margem || 24;
    const lado = onde.split('-')[1];
    const x = lado === 'esq' ? margem : lado === 'dir' ? t.w - margem : t.w / 2;
    const y = onde.startsWith('sup') ? margem + tam * 0.8 : t.h - margem;
    g.append(el('svg:text', {
      x, y, 'text-anchor': lado === 'esq' ? 'start' : lado === 'dir' ? 'end' : 'middle', 'font-size': tam,
      'font-family': FAMILIAS[cfg.fonte] || FAMILIAS.helv, fill: cfg.cor || '#333', text: txt,
    }));
    algum = true;
  };
  const modelo = (m, n, tot) => String(m).replaceAll('{n}', n).replaceAll('{total}', tot).replaceAll('{data}', dataHoje()).replaceAll('{arquivo}', E.nome);
  for (const [k, pos] of [['cabecalho', 'sup'], ['rodape', 'inf']]) {
    const c = D[k];
    if (!c || !alvo(c)) continue;
    const n = idx + (+c.inicio || 1);
    for (const lado of ['esq', 'centro', 'dir']) if (c[lado]) linha(modelo(c[lado], n, total), `${pos}-${lado}`, c, 9);
  }
  const nm = D.numeracao;
  if (nm && alvo(nm)) {
    const ini = +nm.inicio || 1;
    linha(modelo(nm.formato || '{n}', idx + ini, total + ini - 1), nm.posicao || 'inf-centro', nm, 10);
  }
  if (algum) svg.append(g);
}

/* ---------------------------------------------------------------- formulários */
function desenharCampos(div, pg) {
  const inn = div.querySelector('.pg-in');
  $$('.campo', inn).forEach(c => c.remove());
  if (pg.doc === 'branco') return;
  const d = E.docs[pg.doc];
  if (!d || !d.campos || !d.campos.length) return;
  const z = E.zoom;
  const vals = E.campos[pg.doc] || {};
  for (const c of d.campos) {
    if (c.pagina !== pg.p) continue;
    const pos = `left:${c.x * z}px;top:${c.y * z}px;width:${c.w * z}px;height:${c.h * z}px;font-size:${Math.max(7, Math.min(c.h * 0.68, 13)) * z}px`;
    const atual = c.nome in vals ? vals[c.nome] : c.valor;
    let inp;
    if (c.tipo === 'texto') {
      inp = c.multilinha ? el('textarea', { class: 'campo', style: pos }) : el('input', { class: 'campo', type: 'text', style: pos });
      inp.value = atual || '';
      if (c.max) inp.maxLength = c.max;
    } else if (c.tipo === 'caixa' || c.tipo === 'radio') {
      const lado = Math.min(c.w, c.h) * z;
      inp = el('input', { class: 'campo', type: c.tipo === 'caixa' ? 'checkbox' : 'radio', name: pg.uid + c.nome, style: `left:${(c.x + c.w / 2) * z - lado / 2}px;top:${(c.y + c.h / 2) * z - lado / 2}px;width:${lado}px;height:${lado}px` });
      inp.checked = atual === c.on;
    } else if (c.tipo === 'lista') {
      inp = el('select', { class: 'campo', style: pos });
      if (!c.combo || !c.opcoes.some(o => o[0] === '')) inp.append(el('option', { value: '', text: '' }));
      for (const [v, rot] of c.opcoes) inp.append(el('option', { value: v, text: rot }));
      inp.value = atual || '';
    } else continue;
    inp.title = c.nome;
    if (c.somente_leitura) inp.disabled = true;
    const salvar = () => {
      let v;
      if (c.tipo === 'caixa') v = inp.checked ? c.on : 'Off';
      else if (c.tipo === 'radio') { if (!inp.checked) return; v = c.on; }
      else v = inp.value;
      const atualV = (E.campos[pg.doc] || {})[c.nome];
      if (atualV === v) return;
      registrar();
      (E.campos[pg.doc] = E.campos[pg.doc] || {})[c.nome] = v;
      // mesmo campo em outras páginas/duplicatas
      $$(`.pg`).forEach(o => { if (o !== div) { const p2 = paginaPorUid(o.dataset.uid); if (p2 && p2.doc === pg.doc) desenharCampos(o, p2); } });
    };
    inp.addEventListener('change', salvar);
    if (c.tipo === 'texto') inp.addEventListener('blur', salvar);
    inp.addEventListener('pointerdown', e => e.stopPropagation());
    inn.append(inp);
  }
}

/* ---------------------------------------------------------------- miniaturas */
let obsMini;
function renderMiniaturas() {
  const c = $('#miniaturas');
  if (obsMini) obsMini.disconnect();
  obsMini = new IntersectionObserver(ents => {
    for (const en of ents) {
      if (!en.isIntersecting) continue;
      const img = en.target.querySelector('img');
      if (img && !img.src && img.dataset.src) img.src = img.dataset.src;
    }
  }, { root: $('#abaPaginas'), rootMargin: '300px 0px' });
  const frag = document.createDocumentFragment();
  E.paginas.forEach((pg, i) => {
    const b = dimsBase(pg), t = dimsTela(pg);
    const esc = 150 / Math.max(t.w, t.h);
    const cx = el('div', { class: 'cx', style: `width:${t.w * esc}px;height:${t.h * esc}px` });
    if (pg.doc !== 'branco') {
      cx.append(el('img', { alt: '', draggable: 'false', 'data-src': urlPagina(pg, 0.3, 'jpeg'), style: `width:${b.w * esc}px;height:${b.h * esc}px;transform:translate(-50%,-50%) rotate(${pg.rot}deg)` }));
    }
    const m = el('div', { class: 'mini' + (E.sel.has(pg.uid) ? ' sel' : '') + (i === E.atual ? ' atual' : ''), draggable: 'true', 'data-uid': pg.uid },
      cx, el('span', { class: 'num', text: String(i + 1) }), el('div', { class: 'marcas' }));
    frag.append(m);
    obsMini.observe(m);
  });
  c.replaceChildren(frag);
  E.paginas.forEach(p => atualizarMiniaturaMarcas(p.uid));
  atualizarSelInfo();
}
function atualizarMiniaturaMarcas(uid) {
  const m = $(`.mini[data-uid="${uid}"] .marcas`);
  const pg = paginaPorUid(uid);
  if (!m || !pg) return;
  m.replaceChildren(...(pg.itens.length ? [el('i', { title: `${pg.itens.length} anotação(ões)` })] : []));
}
function atualizarSelInfo() {
  const n = E.sel.size;
  $('#selInfo').textContent = n ? `${n} página(s) selecionada(s). Os botões acima valem para elas.` : 'Clique para selecionar; Ctrl ou Shift para várias. Arraste para reordenar.';
  $$('.mini').forEach(m => m.classList.toggle('sel', E.sel.has(m.dataset.uid)));
}
function alvosPaginas() {
  if (E.sel.size) return E.paginas.filter(p => E.sel.has(p.uid));
  return E.paginas[E.atual] ? [E.paginas[E.atual]] : [];
}

function iniciarMiniaturas() {
  const c = $('#miniaturas');
  c.addEventListener('click', e => {
    const m = e.target.closest('.mini');
    if (!m) return;
    const uid = m.dataset.uid, i = indicePorUid(uid);
    if (e.shiftKey && E.ancora !== null) {
      const a = indicePorUid(E.ancora);
      const [x, y] = a < i ? [a, i] : [i, a];
      if (!(e.ctrlKey || e.metaKey)) E.sel.clear();
      for (let k = x; k <= y; k++) E.sel.add(E.paginas[k].uid);
    } else if (e.ctrlKey || e.metaKey) {
      E.sel.has(uid) ? E.sel.delete(uid) : E.sel.add(uid);
      E.ancora = uid;
    } else {
      E.sel = new Set(E.sel.size === 1 && E.sel.has(uid) ? [] : [uid]);
      E.ancora = uid;
      irPara(i);
    }
    atualizarSelInfo();
  });
  let arrastando = null;
  c.addEventListener('dragstart', e => {
    const m = e.target.closest('.mini');
    if (!m) return;
    if (!E.sel.has(m.dataset.uid)) { E.sel = new Set([m.dataset.uid]); atualizarSelInfo(); }
    arrastando = [...E.sel];
    $$('.mini').forEach(x => x.classList.toggle('arrastando', E.sel.has(x.dataset.uid)));
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', 'paginas');
  });
  const limpar = () => $$('.mini').forEach(x => x.classList.remove('alvo-antes', 'alvo-depois', 'arrastando'));
  c.addEventListener('dragover', e => {
    if (!arrastando) return;
    e.preventDefault();
    const m = e.target.closest('.mini');
    $$('.mini').forEach(x => x.classList.remove('alvo-antes', 'alvo-depois'));
    if (!m) return;
    const r = m.getBoundingClientRect();
    m.classList.add(e.clientY < r.top + r.height / 2 ? 'alvo-antes' : 'alvo-depois');
  });
  c.addEventListener('dragend', () => { arrastando = null; limpar(); });
  c.addEventListener('drop', e => {
    if (!arrastando) return;
    e.preventDefault();
    e.stopPropagation();
    const m = e.target.closest('.mini');
    const antes = m && m.classList.contains('alvo-antes');
    const ref = m ? m.dataset.uid : null;
    const movidos = arrastando;
    arrastando = null;
    limpar();
    if (ref && movidos.includes(ref)) return;
    registrar();
    const mover = E.paginas.filter(p => movidos.includes(p.uid));
    E.paginas = E.paginas.filter(p => !movidos.includes(p.uid));
    let pos = ref ? indicePorUid(ref) + (antes ? 0 : 1) : E.paginas.length;
    E.paginas.splice(pos, 0, ...mover);
    E.atual = indicePorUid(mover[0].uid);
    renderTudo();
  });
}

/* operações de página */
function opPagina(op) {
  const alvos = alvosPaginas();
  if (!alvos.length && op !== 'branco' && op !== 'inserir') return;
  if (op === 'inserir') return abrirSeletor('inserir');
  registrar();
  if (op === 'girar-e' || op === 'girar-d') {
    for (const p of alvos) p.rot = (p.rot + (op === 'girar-d' ? 90 : 270)) % 360;
  } else if (op === 'duplicar') {
    const ult = indicePorUid(alvos[alvos.length - 1].uid);
    const copias = alvos.map(p => ({ ...JSON.parse(JSON.stringify(p)), uid: uid('p'), itens: p.itens.map(i => ({ ...JSON.parse(JSON.stringify(i)), id: uid('i') })) }));
    E.paginas.splice(ult + 1, 0, ...copias);
  } else if (op === 'apagar') {
    if (alvos.length >= E.paginas.length) { E.hist.pop(); return aviso('O documento precisa de pelo menos uma página.', 'erro'); }
    const fora = new Set(alvos.map(p => p.uid));
    E.paginas = E.paginas.filter(p => !fora.has(p.uid));
    E.sel.clear();
    if (E.certificado && E.certificado.caixa && fora.has(E.certificado.caixa.pg)) E.certificado.caixa = null;
  } else if (op === 'branco') {
    const ref = E.paginas[E.atual];
    const d = ref ? dimsTela(ref) : { w: 595.28, h: 841.89 };
    E.paginas.splice(E.atual + 1, 0, { uid: uid('p'), doc: 'branco', p: 0, rot: 0, w: d.w, h: d.h, itens: [] });
    E.atual += 1;
  }
  E.atual = clamp(E.atual, 0, E.paginas.length - 1);
  renderTudo();
}

/* ---------------------------------------------------------------- página atual / navegação */
function irPara(i, suave = true) {
  const pg = E.paginas[i];
  if (!pg) return;
  const div = $(`.pg[data-uid="${pg.uid}"]`);
  if (!div) return;
  E.atual = i;
  $('#visor').scrollTo({ top: div.offsetTop - 12, behavior: suave ? 'smooth' : 'auto' });
  marcarAtual();
}
function marcarAtual() {
  $$('.pg').forEach((d, k) => d.classList.toggle('atual', k === E.atual));
  $$('.mini').forEach((d, k) => d.classList.toggle('atual', k === E.atual));
  const ind = $('#pagInd');
  ind.hidden = !E.paginas.length;
  ind.textContent = `Página ${E.atual + 1} de ${E.paginas.length}`;
}
function acompanharRolagem() {
  const v = $('#visor');
  let pend = false;
  v.addEventListener('scroll', () => {
    if (pend) return;
    pend = true;
    requestAnimationFrame(() => {
      pend = false;
      const alvo = v.getBoundingClientRect().top + v.clientHeight * 0.3;
      const pgs = $$('.pg');
      let melhor = 0, dist = Infinity;
      pgs.forEach((d, k) => {
        const r = d.getBoundingClientRect();
        const dd = r.top <= alvo && r.bottom >= alvo ? 0 : Math.min(Math.abs(r.top - alvo), Math.abs(r.bottom - alvo));
        if (dd < dist) { dist = dd; melhor = k; }
      });
      if (melhor !== E.atual) {
        E.atual = melhor;
        marcarAtual();
        const m = $$('.mini')[melhor];
        if (m) {
          const box = $('#abaPaginas'), r = m.getBoundingClientRect(), rb = box.getBoundingClientRect();
          if (r.top < rb.top || r.bottom > rb.bottom) box.scrollTop += r.top - rb.top - rb.height / 3;
        }
      }
    });
  }, { passive: true });
}

/* ---------------------------------------------------------------- ferramentas */
function escolherFerramenta(f) {
  fecharEditores();
  E.ferramenta = f;
  if (f !== 'selecionar') E.item = null;
  $$('#ferramentas button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.f === f)));
  $('#visor').dataset.f = f;
  if (f === 'assinatura' && !E.assinaturaAtiva) {
    const salvas = (E.prefs.assinaturas || []);
    if (salvas.length) E.assinaturaAtiva = salvas[0];
    else dialogoAssinatura();
  }
  if (f === 'imagem' && !E.imagemAtiva) escolherImagem();
  if (f === 'certificado' && !(E.certificado && E.certificado.info)) dialogoCertificado();
  E.paginas.forEach(p => atualizarPagina(p.uid));
  renderProps();
}

function pontoNaPagina(ev, div) {
  const pg = paginaPorUid(div.dataset.uid);
  const b = dimsBase(pg), z = E.zoom;
  const r = div.getBoundingClientRect();
  const dx = ev.clientX - (r.left + r.width / 2), dy = ev.clientY - (r.top + r.height / 2);
  const a = pg.rot * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  const x = dx * c + dy * s, y = -dx * s + dy * c;
  return { x: clamp((x + b.w * z / 2) / z, 0, b.w), y: clamp((y + b.h * z / 2) / z, 0, b.h), pg, b };
}

function novoItem(pg, dados) {
  const it = { id: uid('i'), ...dados };
  pg.itens.push(it);
  return it;
}

function iniciarInteracao() {
  const v = $('#visor');
  let acao = null;

  v.addEventListener('pointerdown', ev => {
    if (ev.button !== 0) return;
    if (E.ferramenta === 'mao') {
      acao = { tipo: 'mao', x: ev.clientX, y: ev.clientY, sl: v.scrollLeft, st: v.scrollTop };
      v.classList.add('arrastando-mao');
      v.setPointerCapture(ev.pointerId);
      return;
    }
    const div = ev.target.closest('.pg');
    if (!div || ev.target.closest('.campo, .editor-texto')) return;
    const pt = pontoNaPagina(ev, div);
    const pg = pt.pg;
    E.atual = indicePorUid(pg.uid);
    marcarAtual();
    const f = E.ferramenta;

    if (f === 'selecionar') {
      const alca = ev.target.closest('[data-alca]');
      const gi = ev.target.closest('[data-item]');
      if (alca && E.item) {
        const s = itemSel();
        registrar();
        acao = { tipo: 'alca', alca: alca.dataset.alca, pg, it: s.it, ini: pt, orig: JSON.parse(JSON.stringify(s.it)), mudou: false };
      } else if (gi) {
        const it = pg.itens.find(i => i.id === gi.dataset.item);
        const antes = E.item;
        E.item = { pg: pg.uid, id: it.id };
        if (!antes || antes.id !== it.id) { if (antes) atualizarPagina(antes.pg); renderProps(); }
        registrar();
        acao = { tipo: 'mover', pg, it, ini: pt, orig: JSON.parse(JSON.stringify(it)), mudou: false };
      } else {
        const antes = E.item;
        E.item = null;
        if (antes) { atualizarPagina(antes.pg); renderProps(); }
        return;
      }
      atualizarPagina(pg.uid);
      div.setPointerCapture(ev.pointerId);
      ev.preventDefault();
      return;
    }
    if (f === 'editar') {
      const o = ev.target.closest('[data-obj]');
      if (o) { ev.preventDefault(); editarOriginal(div, pg, +o.dataset.obj); }
      return;
    }
    ev.preventDefault();
    if (ARRASTAR_CAIXA.has(f) || f === 'linha' || f === 'seta') {
      acao = { tipo: 'caixa', f, pg, div, ini: pt, fim: pt };
    } else if (f === 'caneta') {
      acao = { tipo: 'caneta', pg, div, pontos: [[pt.x, pt.y]] };
    } else if (f === 'texto') {
      registrar();
      const st = E.estilo.texto;
      const it = novoItem(pg, { tipo: 'texto', x: pt.x, y: pt.y - st.tamanho * 0.6, w: Math.min(240, pt.b.w - pt.x - 4), h: st.tamanho * 1.2 + 4, texto: '', linhas: [''], ...st });
      E.item = { pg: pg.uid, id: it.id };
      atualizarPagina(pg.uid);
      editarTextoItem(div, pg, it, true);
      return;
    } else if (f === 'nota') {
      registrar();
      const it = novoItem(pg, { tipo: 'nota', x: pt.x - 4, y: pt.y - 4, texto: '', ...E.estilo.nota });
      E.item = { pg: pg.uid, id: it.id };
      escolherFerramenta('selecionar');
      E.item = { pg: pg.uid, id: it.id };
      atualizarPagina(pg.uid);
      renderProps();
      setTimeout(() => { const t = $('#props textarea'); if (t) t.focus(); }, 30);
      return;
    } else if (f === 'carimbo') {
      registrar();
      const st = E.estilo.carimbo;
      const w = larguraTexto(st.texto, { ...st, negrito: true }) + 10, h = st.tamanho * 1.2 + 8;
      const it = novoItem(pg, { tipo: 'carimbo', x: pt.x - w / 2, y: pt.y - h / 2, w, h, linhas: [st.texto], ...st });
      E.item = { pg: pg.uid, id: it.id };
      atualizarPagina(pg.uid);
      renderProps();
      return;
    } else if (f === 'imagem' || f === 'assinatura') {
      const src = f === 'imagem' ? E.imagemAtiva : E.assinaturaAtiva;
      if (!src) { f === 'imagem' ? escolherImagem() : dialogoAssinatura(); return; }
      const im = new Image();
      im.onload = () => {
        registrar();
        const larg = f === 'assinatura' ? 170 : Math.min(240, pt.b.w * 0.5);
        const w = larg, h = larg * im.naturalHeight / im.naturalWidth;
        const it = novoItem(pg, { tipo: f, x: pt.x - w / 2, y: pt.y - h / 2, w, h, imagem: src, opacidade: 1 });
        E.item = { pg: pg.uid, id: it.id };
        escolherFerramenta('selecionar');
        E.item = { pg: pg.uid, id: it.id };
        atualizarPagina(pg.uid);
        renderProps();
      };
      im.src = src;
      return;
    }
    if (acao) div.setPointerCapture(ev.pointerId);
  });

  v.addEventListener('pointermove', ev => {
    if (!acao) return;
    if (acao.tipo === 'mao') {
      v.scrollLeft = acao.sl - (ev.clientX - acao.x);
      v.scrollTop = acao.st - (ev.clientY - acao.y);
      return;
    }
    const div = $(`.pg[data-uid="${acao.pg.uid}"]`);
    const pt = pontoNaPagina(ev, div);
    if (acao.tipo === 'mover') {
      const dx = pt.x - acao.ini.x, dy = pt.y - acao.ini.y;
      if (Math.abs(dx) + Math.abs(dy) > 0.5) acao.mudou = true;
      moverItem(acao.it, acao.orig, dx, dy);
      atualizarPagina(acao.pg.uid);
    } else if (acao.tipo === 'alca') {
      acao.mudou = true;
      redimensionar(acao.it, acao.orig, acao.alca, pt, ev.shiftKey);
      atualizarPagina(acao.pg.uid);
    } else if (acao.tipo === 'caixa') {
      acao.fim = pt;
      desenharRascunho(div, acao);
    } else if (acao.tipo === 'caneta') {
      const ult = acao.pontos[acao.pontos.length - 1];
      if (Math.hypot(pt.x - ult[0], pt.y - ult[1]) > 0.8 / E.zoom * 2) acao.pontos.push([+pt.x.toFixed(2), +pt.y.toFixed(2)]);
      desenharRascunho(div, acao);
    }
  });

  const terminar = () => {
    if (!acao) return;
    const a = acao;
    acao = null;
    if (a.tipo === 'mao') { v.classList.remove('arrastando-mao'); return; }
    const div = $(`.pg[data-uid="${a.pg.uid}"]`);
    const r = div && div.querySelector('.rascunho-g');
    if (r) r.remove();
    if (a.tipo === 'mover' || a.tipo === 'alca') {
      if (!a.mudou) E.hist.pop();
      if (a.it.tipo === 'texto' && a.tipo === 'alca') rewrap(a.it);
      atualizarPagina(a.pg.uid);
      renderProps();
      atualizarBotoes();
      return;
    }
    if (a.tipo === 'caixa') {
      const x = Math.min(a.ini.x, a.fim.x), y = Math.min(a.ini.y, a.fim.y);
      let w = Math.abs(a.fim.x - a.ini.x), h = Math.abs(a.fim.y - a.ini.y);
      if (a.f === 'linha' || a.f === 'seta') {
        if (Math.hypot(w, h) < 3) return;
        registrar();
        const it = novoItem(a.pg, { tipo: a.f, pontos: [[a.ini.x, a.ini.y], [a.fim.x, a.fim.y]], ...E.estilo[a.f] });
        E.item = { pg: a.pg.uid, id: it.id };
      } else if (a.f === 'certificado') {
        if (w < 20 || h < 10) { w = 200; h = 60; }
        E.certificado = { ...(E.certificado || {}), caixa: { pg: a.pg.uid, x: Math.min(x, a.ini.b.w - w), y: Math.min(y, a.ini.b.h - h), w, h } };
        renderFaixas();
        if (!E.certificado.info) dialogoCertificado();
        else aviso('Posição da assinatura digital definida. Ela é aplicada quando você salvar.', 'ok');
      } else {
        if (w < 2 || h < 2) {
          if (['marca', 'sublinhado', 'tachado'].includes(a.f)) return;
          return;
        }
        registrar();
        const it = novoItem(a.pg, { tipo: a.f, x, y, w, h, ...(E.estilo[a.f] || {}) });
        E.item = { pg: a.pg.uid, id: it.id };
      }
      atualizarPagina(a.pg.uid);
      renderProps();
      return;
    }
    if (a.tipo === 'caneta') {
      if (a.pontos.length < 2) a.pontos.push([a.pontos[0][0] + 0.3, a.pontos[0][1]]);
      registrar();
      const ult = a.pg.itens[a.pg.itens.length - 1];
      const st = E.estilo.caneta;
      // traços seguidos com a mesma caneta formam um só desenho
      if (ult && ult.tipo === 'caneta' && ult._agora && Date.now() - ult._agora < 1800 && ult.cor === st.cor && ult.espessura === st.espessura) {
        ult.tracos.push(a.pontos);
        ult._agora = Date.now();
      } else {
        novoItem(a.pg, { tipo: 'caneta', tracos: [a.pontos], ...st, _agora: Date.now() });
      }
      atualizarPagina(a.pg.uid);
    }
  };
  v.addEventListener('pointerup', terminar);
  v.addEventListener('pointercancel', terminar);

  v.addEventListener('dblclick', ev => {
    const gi = ev.target.closest('[data-item]');
    const div = ev.target.closest('.pg');
    if (!gi || !div) return;
    const pg = paginaPorUid(div.dataset.uid);
    const it = pg.itens.find(i => i.id === gi.dataset.item);
    if (it && it.tipo === 'texto') editarTextoItem(div, pg, it, false);
    if (it && it.tipo === 'nota') { const t = $('#props textarea'); if (t) t.focus(); }
  });

  v.addEventListener('wheel', ev => {
    if (!(ev.ctrlKey || ev.metaKey)) return;
    ev.preventDefault();
    passoZoom(ev.deltaY < 0 ? 1 : -1);
  }, { passive: false });
}

function desenharRascunho(div, a) {
  const svg = div.querySelector('svg.camada');
  let g = svg.querySelector('.rascunho-g');
  if (!g) { g = el('svg:g', { class: 'rascunho-g' }); svg.append(g); }
  g.replaceChildren();
  if (a.tipo === 'caneta') {
    const st = E.estilo.caneta;
    g.append(el('svg:polyline', { points: a.pontos.map(p => p.join(',')).join(' '), stroke: st.cor, 'stroke-width': st.espessura, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', opacity: st.opacidade }));
    return;
  }
  if (a.f === 'linha' || a.f === 'seta') {
    g.append(el('svg:line', { x1: a.ini.x, y1: a.ini.y, x2: a.fim.x, y2: a.fim.y, stroke: E.estilo[a.f].cor, 'stroke-width': E.estilo[a.f].espessura }));
    return;
  }
  const x = Math.min(a.ini.x, a.fim.x), y = Math.min(a.ini.y, a.fim.y);
  g.append(el('svg:rect', { class: 'rascunho', x, y, width: Math.abs(a.fim.x - a.ini.x), height: Math.abs(a.fim.y - a.ini.y) }));
}

function moverItem(it, o, dx, dy) {
  if (it.tipo === 'linha' || it.tipo === 'seta') it.pontos = o.pontos.map(p => [p[0] + dx, p[1] + dy]);
  else if (it.tipo === 'caneta') it.tracos = o.tracos.map(t => t.map(p => [p[0] + dx, p[1] + dy]));
  else { it.x = o.x + dx; it.y = o.y + dy; }
}

function redimensionar(it, o, alca, pt, proporcional) {
  if (alca === 'p0' || alca === 'p1') {
    it.pontos = o.pontos.map(p => p.slice());
    it.pontos[+alca[1]] = [pt.x, pt.y];
    return;
  }
  const bb = caixaItem(o);
  let w = Math.max(4, pt.x - bb.x), h = Math.max(4, pt.y - bb.y);
  if (proporcional || it.tipo === 'assinatura' || it.tipo === 'imagem') {
    const r = bb.h / Math.max(bb.w, 0.01);
    if (!(proporcional === false && it.tipo === 'imagem')) h = w * r;
  }
  if (it.tipo === 'caneta') {
    const sx = w / Math.max(bb.w, 0.01), sy = h / Math.max(bb.h, 0.01);
    it.tracos = o.tracos.map(t => t.map(p => [bb.x + (p[0] - bb.x) * sx, bb.y + (p[1] - bb.y) * sy]));
    return;
  }
  if (it.tipo === 'carimbo') {
    const esc = w / bb.w;
    it.tamanho = clamp(o.tamanho * esc, 5, 200);
    it.w = larguraTexto(it.linhas[0], { ...it, negrito: true }) + 10;
    it.h = it.tamanho * 1.2 + 8;
    return;
  }
  it.w = w;
  it.h = h;
}

function rewrap(it) {
  it.linhas = quebrarLinhas(it.texto || '', it, Math.max(10, it.w - 4));
  it.h = Math.max(it.h, it.linhas.length * it.tamanho * 1.2 + 4);
}

/* ---------------------------------------------------------------- editores de texto */
function fecharEditores() {
  $$('.editor-texto').forEach(t => t.dispatchEvent(new Event('fechar')));
}

function editarTextoItem(div, pg, it, novo) {
  fecharEditores();
  const z = E.zoom, inn = div.querySelector('.pg-in');
  const t = el('textarea', { class: 'editor-texto', spellcheck: 'true' });
  t.value = it.texto || '';
  const ajustar = () => {
    t.style.cssText = `left:${it.x * z}px;top:${it.y * z}px;width:${it.w * z}px;min-height:${it.tamanho * 1.2 * z + 4 * z}px;` +
      `font:${cssFonte(it, it.tamanho * z)};line-height:1.2;padding:${2 * z}px;color:${it.cor}`;
    t.style.height = 'auto';
    t.style.height = t.scrollHeight + 'px';
  };
  ajustar();
  inn.append(t);
  t.focus();
  if (!novo) t.select();
  let fechado = false;
  const fechar = (salvar = true) => {
    if (fechado) return;
    fechado = true;
    t.remove();
    if (!salvar) { if (novo) { pg.itens = pg.itens.filter(i => i !== it); E.item = null; E.hist.pop(); } atualizarPagina(pg.uid); atualizarBotoes(); return; }
    const v = t.value.replace(/\s+$/, '');
    if (!v) {
      pg.itens = pg.itens.filter(i => i !== it);
      if (novo) E.hist.pop();
      E.item = null;
    } else if (v !== it.texto) {
      if (!novo) registrar();
      it.texto = v;
      const larg = Math.max(...v.split('\n').map(l => larguraTexto(l, it))) + 6;
      if (novo) it.w = clamp(larg, 30, Math.max(30, dimsBase(pg).w - it.x - 2));
      it.linhas = quebrarLinhas(v, it, Math.max(10, it.w - 4));
      it.h = it.linhas.length * it.tamanho * 1.2 + 4;
    }
    atualizarPagina(pg.uid);
    renderProps();
    atualizarBotoes();
  };
  t.addEventListener('input', ajustar);
  t.addEventListener('blur', () => fechar(true));
  t.addEventListener('fechar', () => fechar(true));
  t.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Escape') { e.preventDefault(); fechar(!novo || !!t.value.trim()); }
  });
  t.addEventListener('pointerdown', e => e.stopPropagation());
}

async function carregarObjetos(pg) {
  const chave = `${pg.doc}|${pg.p}`;
  if (E.objetos[chave] !== undefined) return;
  E.objetos[chave] = null;
  try {
    E.objetos[chave] = await api(`/api/objetos?doc=${pg.doc}&p=${pg.p}`);
  } catch (e) { E.objetos[chave] = []; erro(e); }
  E.paginas.filter(p => `${p.doc}|${p.p}` === chave).forEach(p => atualizarPagina(p.uid));
  if (E.objetos[chave] && !E.objetos[chave].length && E.ferramenta === 'editar') {
    aviso('Esta página não tem texto editável. Se for escaneada, use Documento > Reconhecer texto (OCR) primeiro.', '', 7000);
  }
}

function editarOriginal(div, pg, objId) {
  fecharEditores();
  const objs = E.objetos[`${pg.doc}|${pg.p}`] || [];
  const o = objs.find(x => x.id === objId);
  if (!o) return;
  const z = E.zoom, inn = div.querySelector('.pg-in');
  const fam = FONTE_PDF_PARA_FAMILIA(o.fonte);
  const a = { fonte: fam, negrito: /bold/i.test(o.fonte), italico: /italic|oblique/i.test(o.fonte), tamanho: o.tamanho };
  const varias = (o.linhas || 1) > 1;
  const vert = o.h > o.w * 2.5 && o.texto.length > 3;  // texto em página girada: edita na horizontal mesmo
  const largura = vert ? Math.max(o.h, 200) : o.w;
  const entre = o.entrelinha && varias ? o.entrelinha : o.tamanho * 1.2;
  const t = el('textarea', { class: 'editor-texto original' + (varias ? ' bloco' : ''), spellcheck: 'true', rows: 1 });
  t.value = o.texto;
  t.style.cssText = `left:${o.x * z - 4}px;top:${o.y * z - 4}px;width:${largura * z + 10}px;` +
    `font:${cssFonte(a, o.tamanho * z)};line-height:${entre * z}px;color:${o.cor};padding:3px 4px;` +
    `text-align:${{ centro: 'center', direita: 'right' }[o.alinhamento] || 'left'}`;
  const dica = el('div', { class: 'editor-dica', text: 'Enter: nova linha · Ctrl+Enter ou clique fora: aplicar · Esc: cancelar' });
  const ajustar = () => {
    if (!varias) t.style.width = Math.max(largura * z + 10, larguraTexto(t.value.split('\n').reduce((m, l) => (l.length > m.length ? l : m), ''), { ...a, tamanho: o.tamanho * z }) + 18) + 'px';
    t.style.height = 'auto';
    t.style.height = Math.max(t.scrollHeight, (vert ? o.tamanho * 1.3 : o.h) * z + 8) + 'px';
    dica.style.cssText = `left:${o.x * z - 4}px;top:${o.y * z - 4 + t.offsetHeight + 4}px`;
  };
  inn.append(t, dica);
  ajustar();
  t.focus();
  t.setSelectionRange(t.value.length, t.value.length);
  let fechado = false;
  const fechar = async salvar => {
    if (fechado) return;
    fechado = true;
    const novo = t.value.replace(/[ \t]+\n/g, '\n').trim();
    t.remove();
    dica.remove();
    if (!salvar || novo === o.texto.trim()) return;
    try {
      const r = await ocupado('Editando o texto…', () => api('/api/editar-texto', { metodo: 'POST', json: { doc: pg.doc, p: pg.p, edicoes: [{ id: o.id, ids: o.ids, texto: novo }] } }));
      trocarDoc(pg.doc, r);
      aviso(novo ? 'Texto alterado. Se a fonte original não tinha alguma letra, usei a fonte padrão mais parecida.' : 'Texto apagado.', 'ok');
    } catch (e) { erro(e); }
  };
  t.addEventListener('input', ajustar);
  t.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fechar(true); }
    if (e.key === 'Escape') { e.preventDefault(); fechar(false); }
  });
  t.addEventListener('blur', () => fechar(true));
  t.addEventListener('fechar', () => fechar(false));
  t.addEventListener('pointerdown', e => e.stopPropagation());
}

/* Uma operação criou uma versão nova do documento (edição de texto, OCR). */
function trocarDoc(velho, novo, semHistorico = false) {
  if (!semHistorico) registrar();
  E.docs[novo.id] = novo;
  for (const p of E.paginas) if (p.doc === velho) p.doc = novo.id;
  if (E.campos[velho]) E.campos[novo.id] = JSON.parse(JSON.stringify(E.campos[velho]));
  for (const k of Object.keys(E.objetos)) if (k.startsWith(velho + '|')) delete E.objetos[k];
  E.acertos = [];
  renderTudo();
}

/* ---------------------------------------------------------------- painel de propriedades */
function controleCor(atual, aoMudar, lista = CORES, nenhuma = false) {
  const box = el('div', { class: 'cores' });
  if (nenhuma) box.append(el('button', { type: 'button', class: 'nenhuma', title: 'Sem cor', 'aria-pressed': String(!atual), onclick: () => aoMudar(null) }));
  for (const c of lista) box.append(el('button', { type: 'button', style: `background:${c}`, title: c, 'aria-pressed': String((atual || '').toLowerCase() === c), onclick: () => aoMudar(c) }));
  const inp = el('input', { type: 'color', value: atual && atual.length === 7 ? atual : '#000000', title: 'Outra cor' });
  inp.addEventListener('change', () => aoMudar(inp.value));
  box.append(inp);
  return box;
}
function rotulo(txt, ...filhos) { return el('label', { class: 'campo-p' }, txt, ...filhos); }
function faixa(min, max, passo, valor, aoMudar, fmt = v => v) {
  const out = el('span', { text: fmt(valor) });
  const r = el('input', { type: 'range', min, max, step: passo, value: valor });
  let primeiro = true;
  r.addEventListener('input', () => { out.textContent = fmt(+r.value); aoMudar(+r.value, primeiro); primeiro = false; });
  r.addEventListener('change', () => { primeiro = true; });
  return [r, out];
}

function renderProps() {
  const p = $('#props');
  if (!p) return;
  const s = itemSel();
  const f = E.ferramenta;
  const alvo = s ? s.it : E.estilo[f];
  const tipo = s ? s.it.tipo : f;
  const titulo = s ? (NOMES_F[tipo] || 'Item') : (NOMES_F[f] || '');
  const corpo = [];
  // altera o item selecionado (com desfazer) ou o estilo da ferramenta
  const mudar = (k, v, agrupar = false) => {
    if (s) {
      if (!agrupar) registrar();
      s.it[k] = v;
      if (s.it.tipo === 'texto' && ['tamanho', 'fonte', 'negrito', 'italico'].includes(k)) rewrap(s.it);
      if (s.it.tipo === 'carimbo' && ['tamanho', 'texto', 'fonte'].includes(k)) {
        if (k === 'texto') s.it.linhas = [v];
        s.it.w = larguraTexto(s.it.linhas[0], { ...s.it, negrito: true }) + 10;
        s.it.h = s.it.tamanho * 1.2 + 8;
      }
      atualizarPagina(s.pg.uid);
    } else if (alvo) alvo[k] = v;
    if (k !== 'texto') renderProps();
  };
  const dicas = {
    selecionar: 'Clique numa anotação para mover, mudar o tamanho ou as cores. Delete apaga.',
    mao: 'Arraste para mover a página na tela.',
    editar: 'Clique num parágrafo com contorno laranja para reescrevê-lo inteiro. As linhas são refeitas na mesma largura, com a mesma posição, tamanho e cor. Enter cria uma linha nova; Ctrl+Enter ou clicar fora aplica.',
    texto: 'Clique na página para escrever.',
    marca: 'Arraste sobre o trecho que quer destacar.',
    sublinhado: 'Arraste sobre o trecho.', tachado: 'Arraste sobre o trecho.',
    nota: 'Clique onde quer deixar o comentário.',
    caneta: 'Desenhe à mão livre.',
    retangulo: 'Arraste para desenhar.', elipse: 'Arraste para desenhar.', linha: 'Arraste do início ao fim.', seta: 'Arraste do início até a ponta.',
    carimbo: 'Clique para carimbar.',
    imagem: 'Clique na página para colocar a imagem.',
    corretivo: 'Cobre com uma cor sólida. O que está embaixo continua no arquivo: para apagar de verdade, use a tarja.',
    tarja: 'Arraste sobre o que deve sumir. Ao salvar, a página vira imagem e o conteúdo sob a tarja deixa de existir no arquivo.',
    certificado: 'Arraste para marcar onde a assinatura digital aparece. Ela é aplicada ao salvar.',
  };
  if (!s && dicas[f]) corpo.push(el('p', { class: 'dica' + (f === 'tarja' || f === 'corretivo' ? ' alerta' : ''), text: dicas[f] }));

  if (alvo) {
    if ('cor' in alvo && tipo !== 'imagem' && tipo !== 'assinatura') {
      const lista = tipo === 'marca' || tipo === 'nota' ? CORES_MARCA : CORES;
      corpo.push(rotulo(tipo === 'corretivo' ? 'Cor de cobertura' : 'Cor', controleCor(alvo.cor, c => mudar('cor', c || '#000000'), lista)));
    }
    if ('preenchimento' in alvo) corpo.push(rotulo('Preenchimento', controleCor(alvo.preenchimento, c => mudar('preenchimento', c), CORES, true)));
    if ('espessura' in alvo) corpo.push(rotulo('Espessura', ...faixa(0.5, 12, 0.5, alvo.espessura, (v, p) => mudar('espessura', v, !p), v => v + ' pt')));
    if ('opacidade' in alvo) corpo.push(rotulo('Opacidade', ...faixa(0.05, 1, 0.05, alvo.opacidade ?? 1, (v, p) => mudar('opacidade', v, !p), v => Math.round(v * 100) + '%')));
    if (tipo === 'texto' || tipo === 'carimbo') {
      const fonte = el('select', {}, ...[['helv', 'Sem serifa (Helvetica)'], ['times', 'Com serifa (Times)'], ['cour', 'Máquina de escrever (Courier)']].map(([v, t]) => el('option', { value: v, text: t })));
      fonte.value = alvo.fonte || 'helv';
      fonte.addEventListener('change', () => mudar('fonte', fonte.value));
      corpo.push(rotulo('Fonte', fonte));
      const tam = el('input', { type: 'number', min: 4, max: 200, step: 1, value: Math.round(alvo.tamanho * 10) / 10 });
      tam.addEventListener('change', () => mudar('tamanho', clamp(+tam.value || 12, 4, 200)));
      corpo.push(rotulo('Tamanho', tam));
      if (tipo === 'texto') {
        const seg = el('div', { class: 'seg' },
          el('button', { type: 'button', 'aria-pressed': String(!!alvo.negrito), onclick: () => mudar('negrito', !alvo.negrito) }, el('b', { text: 'N' })),
          el('button', { type: 'button', 'aria-pressed': String(!!alvo.italico), onclick: () => mudar('italico', !alvo.italico) }, el('i', { text: 'I' })));
        corpo.push(rotulo('Estilo', seg));
        corpo.push(rotulo('Fundo', controleCor(alvo.fundo, c => mudar('fundo', c), ['#ffffff', '#fff6bf', '#e2f0ff', '#e6f7ec'], true)));
        const borda = el('input', { type: 'checkbox' });
        borda.checked = !!alvo.borda;
        borda.addEventListener('change', () => mudar('borda', borda.checked));
        corpo.push(el('label', { class: 'campo-p', style: 'flex-direction:row;align-items:center;gap:8px' }, borda, 'Borda'));
      }
      if (tipo === 'carimbo') {
        const txt = el('input', { type: 'text', value: alvo.texto || (alvo.linhas || [''])[0], maxlength: 60, list: 'carimbosLista' });
        const dl = el('datalist', { id: 'carimbosLista' }, ...['APROVADO', 'RECEBIDO', 'PAGO', 'CONFIDENCIAL', 'REPROVADO', 'CÓPIA', 'URGENTE', 'CANCELADO', `CONFERIDO ${dataHoje()}`].map(v => el('option', { value: v })));
        txt.addEventListener('change', () => mudar('texto', txt.value.trim() || 'APROVADO'));
        corpo.push(rotulo('Texto do carimbo', txt, dl));
      }
    }
    if (tipo === 'nota') {
      const ta = el('textarea', { placeholder: 'Escreva o comentário' });
      ta.value = alvo.texto || '';
      ta.addEventListener('change', () => mudar('texto', ta.value));
      ta.addEventListener('keydown', e => e.stopPropagation());
      corpo.push(rotulo('Comentário', ta));
    }
  }
  if (!s && f === 'assinatura') corpo.push(...painelAssinaturas());
  if (!s && f === 'imagem') corpo.push(el('button', { class: 'btn', type: 'button', onclick: escolherImagem }, icone('imagem'), E.imagemAtiva ? 'Trocar imagem' : 'Escolher imagem'));
  if (!s && f === 'certificado') {
    const c = E.certificado;
    corpo.push(c && c.info ? el('div', { class: 'cert-info' }, el('b', { text: c.info.nome }), el('div', { class: 'muted', text: c.info.icp_brasil ? 'Certificado ICP-Brasil' : 'Certificado' })) : el('p', { class: 'muted', text: 'Nenhum certificado escolhido.' }),
      el('button', { class: 'btn', type: 'button', onclick: dialogoCertificado }, icone('certificado'), c && c.info ? 'Opções da assinatura' : 'Escolher certificado'));
  }
  if (s) {
    const fixo = el('input', { type: 'checkbox' });
    fixo.checked = !!s.it.fixo || ['assinatura', 'corretivo', 'tarja'].includes(s.it.tipo);
    fixo.disabled = ['assinatura', 'corretivo', 'tarja'].includes(s.it.tipo);
    fixo.addEventListener('change', () => mudar('fixo', fixo.checked));
    if (s.it.tipo !== 'tarja') corpo.push(el('label', { class: 'campo-p', style: 'flex-direction:row;align-items:center;gap:8px', title: 'Incorporada ao conteúdo da página: não pode ser movida nem apagada em outros programas.' }, fixo, 'Fixar na página'));
    corpo.push(el('div', { class: 'linha-props' },
      el('button', { class: 'btn mini', type: 'button', onclick: duplicarItem }, icone('copiar'), 'Duplicar'),
      el('button', { class: 'btn mini perigo', type: 'button', onclick: apagarItem }, icone('lixo'), 'Apagar')));
  }
  p.replaceChildren(el('h3', { text: titulo }), ...corpo);
}

function painelAssinaturas() {
  const salvas = E.prefs.assinaturas || [];
  const lista = el('div', { class: 'assin-lista' });
  const todas = [...new Set([...(E.assinaturaAtiva ? [E.assinaturaAtiva] : []), ...salvas])];
  for (const a of todas) {
    const b = el('div', { class: 'assin', role: 'button', 'aria-pressed': String(a === E.assinaturaAtiva), onclick: () => { E.assinaturaAtiva = a; renderProps(); } }, el('img', { src: a, alt: 'Assinatura' }));
    if (salvas.includes(a)) b.append(el('button', { class: 'x', type: 'button', title: 'Esquecer esta assinatura', onclick: ev => { ev.stopPropagation(); esquecerAssinatura(a); } }, icone('fechar')));
    lista.append(b);
  }
  return [lista, el('button', { class: 'btn', type: 'button', onclick: dialogoAssinatura }, icone('mais'), 'Nova assinatura'),
    el('p', { class: 'dica', style: 'margin-top:12px', text: 'Clique na página para assinar. Esta é uma assinatura visual (como no papel). Para validade jurídica digital, use o certificado digital.' })];
}

async function esquecerAssinatura(a) {
  E.prefs.assinaturas = (E.prefs.assinaturas || []).filter(x => x !== a);
  if (E.assinaturaAtiva === a) E.assinaturaAtiva = null;
  await salvarPrefs();
  renderProps();
}

function apagarItem() {
  const s = itemSel();
  if (!s) return;
  registrar();
  s.pg.itens = s.pg.itens.filter(i => i !== s.it);
  E.item = null;
  atualizarPagina(s.pg.uid);
  renderProps();
}
function duplicarItem() {
  const s = itemSel();
  if (!s) return;
  registrar();
  const c = JSON.parse(JSON.stringify(s.it));
  c.id = uid('i');
  moverItem(c, JSON.parse(JSON.stringify(c)), 12, 12);
  s.pg.itens.push(c);
  E.item = { pg: s.pg.uid, id: c.id };
  atualizarPagina(s.pg.uid);
  renderProps();
}

/* ---------------------------------------------------------------- faixas de aviso */
function renderFaixas() {
  const f = $('#faixas');
  const lista = [];
  const docsUsados = [...new Set(E.paginas.map(p => p.doc))].map(d => E.docs[d]).filter(Boolean);
  const comCampos = docsUsados.filter(d => d.campos && d.campos.length);
  if (comCampos.length) lista.push(el('div', { class: 'faixa' }, icone('texto'), 'Este PDF tem formulário: preencha direto nos campos destacados em azul.'));
  const assinados = docsUsados.filter(d => d.assinaturas && d.assinaturas.length);
  if (assinados.length) lista.push(el('div', { class: 'faixa alerta' }, icone('escudo'),
    `Este PDF tem ${assinados.reduce((n, d) => n + d.assinaturas.length, 0)} assinatura(s) digital(is). Salvar com mudanças cria um arquivo novo em que elas deixam de valer.`,
    el('button', { class: 'btn mini', type: 'button', onclick: () => mostrarAba('info') }, 'Ver assinaturas')));
  const semTexto = docsUsados.filter(d => !d.tem_texto && d.paginas.length);
  if (semTexto.length && E.ocr.ok) lista.push(el('div', { class: 'faixa' }, icone('ocr'), 'Parece um documento escaneado (sem texto). O OCR deixa o texto pesquisável e editável.',
    el('button', { class: 'btn mini', type: 'button', onclick: () => dialogoOCR() }, 'Reconhecer texto')));
  if (E.certificado && E.certificado.info) lista.push(el('div', { class: 'faixa' }, icone('certificado'),
    `Ao salvar, o documento será assinado digitalmente por ${E.certificado.info.nome}${E.certificado.caixa ? '' : ' (assinatura invisível)'}.`,
    el('button', { class: 'btn mini', type: 'button', onclick: () => { E.certificado = null; renderFaixas(); E.paginas.forEach(p => atualizarPagina(p.uid)); } }, 'Cancelar')));
  f.replaceChildren(...lista);
}

function atualizarBotoes() {
  $('#btDesfazer').disabled = !E.hist.length;
  $('#btRefazer').disabled = !E.fut.length;
  $('#btSalvar').disabled = !E.paginas.length;
}
