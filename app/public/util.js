/* Bravo PDF: utilidades (servidor local, avisos, arquivos, medidas de texto). */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const NS = 'http://www.w3.org/2000/svg';

function el(tag, attrs = {}, ...filhos) {
  const e = tag.startsWith('svg:') ? document.createElementNS(NS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') e.setAttribute('class', v);
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) e.append(f);
  return e;
}

function icone(nome) {
  const s = document.createElementNS(NS, 'svg');
  const u = document.createElementNS(NS, 'use');
  u.setAttribute('href', '#i-' + nome);
  s.append(u);
  return s;
}

let uidN = 0;
const uid = (p = 'u') => p + (++uidN).toString(36) + Math.random().toString(36).slice(2, 6);

/* ---------- servidor local ---------- */
class ErroApi extends Error {
  constructor(msg, status, dados) { super(msg); this.status = status; this.dados = dados || {}; }
}

async function api(rota, { metodo = 'GET', json, corpo, cabecalhos = {}, tipo = 'json' } = {}) {
  const op = { method: metodo, headers: { ...cabecalhos }, credentials: 'same-origin', cache: 'no-store' };
  if (metodo !== 'GET') op.headers['X-Bravo'] = '1';
  if (json !== undefined) { op.body = JSON.stringify(json); op.headers['Content-Type'] = 'application/json'; }
  else if (corpo !== undefined) op.body = corpo;
  let r;
  try { r = await fetch(rota, op); }
  catch (e) { throw new ErroApi('O Bravo PDF parou de responder. Feche e abra de novo.', 0); }
  if (!r.ok) {
    let d = {};
    try { d = await r.json(); } catch (_) { /* sem corpo */ }
    throw new ErroApi(d.erro || `Falhou (${r.status}).`, r.status, d);
  }
  if (tipo === 'blob') return r.blob();
  if (tipo === 'texto') return r.text();
  return r.json();
}

/* ---------- avisos e espera ---------- */
let avisoTimer;
function aviso(texto, tipo = '', ms = 4500) {
  const a = $('#aviso');
  a.textContent = texto;
  a.className = 'aviso' + (tipo ? ' ' + tipo : '');
  a.hidden = false;
  clearTimeout(avisoTimer);
  if (ms) avisoTimer = setTimeout(() => { a.hidden = true; }, ms);
}
function erro(e) {
  console.error(e);
  aviso(e && e.message ? e.message : String(e), 'erro', 8000);
}

async function ocupado(texto, tarefaFn, comProgresso = false) {
  const box = $('#ocupado');
  $('#ocupadoTxt').textContent = texto;
  const barra = $('#ocupadoProg');
  barra.style.width = '0';
  barra.parentElement.hidden = !comProgresso;
  box.hidden = false;
  const tarefa = uid('t');
  let vivo = true;
  if (comProgresso) {
    (async () => {
      while (vivo) {
        await new Promise(r => setTimeout(r, 700));
        if (!vivo) break;
        try {
          const p = (await api('/api/progresso?tarefa=' + tarefa)).progresso;
          if (p && p[1]) barra.style.width = Math.round(100 * p[0] / p[1]) + '%';
        } catch (_) { /* segue */ }
      }
    })();
  }
  try { return await tarefaFn(tarefa); }
  finally { vivo = false; box.hidden = true; }
}

/* ---------- arquivos ---------- */
function lerArquivo(f, como = 'buffer') {
  return new Promise((ok, falha) => {
    const r = new FileReader();
    r.onload = () => ok(r.result);
    r.onerror = () => falha(new Error('Não consegui ler o arquivo.'));
    if (como === 'dataurl') r.readAsDataURL(f); else r.readAsArrayBuffer(f);
  });
}

function base64DeBuffer(buf) {
  const b = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
}

const TIPOS_SALVAR = {
  pdf: { description: 'Documento PDF', accept: { 'application/pdf': ['.pdf'] } },
  zip: { description: 'Arquivo ZIP', accept: { 'application/zip': ['.zip'] } },
  txt: { description: 'Texto', accept: { 'text/plain': ['.txt'] } },
};

/* Salva um arquivo onde a pessoa escolher (janela do próprio sistema). */
async function salvarArquivo(blob, nome, tipo = 'pdf') {
  if (window.showSaveFilePicker) {
    try {
      const h = await window.showSaveFilePicker({ suggestedName: nome, types: [TIPOS_SALVAR[tipo]] });
      const w = await h.createWritable();
      await w.write(blob);
      await w.close();
      return true;
    } catch (e) {
      if (e && e.name === 'AbortError') return false;
      /* sem permissão para a API: cai no download comum */
    }
  }
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: nome });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return true;
}

function nomeBase(n) { return (n || 'documento').replace(/\.(pdf|png|jpe?g|webp|tiff?|gif|bmp)$/i, ''); }

/* ---------- texto (mesmas fontes padrão que o PDF usa) ---------- */
const FAMILIAS = {
  helv: 'Helvetica, Arial, "Liberation Sans", "Nimbus Sans", sans-serif',
  times: '"Times New Roman", Times, "Liberation Serif", "Nimbus Roman", serif',
  cour: '"Courier New", Courier, "Liberation Mono", "Nimbus Mono PS", monospace',
};
const FONTE_PDF_PARA_FAMILIA = n => (/courier/i.test(n) ? 'cour' : /times/i.test(n) ? 'times' : 'helv');
const medidor = document.createElement('canvas').getContext('2d');
function cssFonte(a, tam) {
  return `${a.italico ? 'italic ' : ''}${a.negrito ? 'bold ' : ''}${tam}px ${FAMILIAS[a.fonte] || FAMILIAS.helv}`;
}
function quebrarLinhas(texto, a, largura) {
  medidor.font = cssFonte(a, a.tamanho);
  const linhas = [];
  for (const par of String(texto).split('\n')) {
    let atual = '';
    for (const palavra of par.split(/(\s+)/)) {
      const t = atual + palavra;
      if (medidor.measureText(t).width <= largura || !atual) { atual = t; continue; }
      linhas.push(atual.replace(/\s+$/, ''));
      atual = palavra.replace(/^\s+/, '');
      while (medidor.measureText(atual).width > largura && atual.length > 1) {  // palavra maior que a caixa
        let k = atual.length - 1;
        while (k > 1 && medidor.measureText(atual.slice(0, k)).width > largura) k--;
        linhas.push(atual.slice(0, k));
        atual = atual.slice(k);
      }
    }
    linhas.push(atual);
  }
  return linhas;
}
function larguraTexto(t, a) { medidor.font = cssFonte(a, a.tamanho); return medidor.measureText(t).width; }

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const dataHoje = () => new Date().toLocaleDateString('pt-BR');

/* intervalos tipo "1-3, 5, 8-10" → índices (base 0) */
function lerIntervalos(texto, total) {
  const grupos = [];
  for (const parte of String(texto).split(/[,;]+/)) {
    const m = parte.trim().match(/^(\d+)\s*(?:-\s*(\d+))?$/);
    if (!m) { if (parte.trim()) return null; continue; }
    let a = +m[1], b = m[2] ? +m[2] : a;
    if (a > b) [a, b] = [b, a];
    if (a < 1 || b > total) return null;
    const g = [];
    for (let i = a; i <= b; i++) g.push(i - 1);
    grupos.push(g);
  }
  return grupos;
}
