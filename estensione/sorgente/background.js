// Rendiconto SW – estensione del browser (M8, allineata al PoC chiuso il 05/10/2026).
// Unico sorgente per Chrome, Edge (MV3 service worker) e Firefox (MV3 background script).
//
// Privacy (verificata dai test e dal PoC):
//  - nessun permesso «tabs»: host_permissions = soli domini della mappatura del CED;
//  - dell'indirizzo si usa solo il nome host, confrontato in memoria e subito scartato;
//  - pagine fuori elenco / interne: URL non visibile → solo diagnostica «url_non_visibile», MAI «web_generico»
//    (decisione del 05/10/2026: web_generico non è più misurabile dall'estensione; l'aggregatore non tratta
//    l'assenza come inattività);
//  - in memoria, storage e messaggi: solo id di sito (a-z0-9_) e contatori numerici;
//  - nessuna rete, nessun content script: solo Native Messaging verso l'host locale;
//  - si campiona solo se l'host conferma raccolta attiva (dopo «Avvia giornata», mai in pausa).
// Note operative (dal PoC): Chrome non ricarica il codice di un'estensione non pacchettizzata al riavvio
// (serve chrome.runtime.reload()); i sotto-processi PowerShell devono usare CREATE_NO_WINDOW per non rubare il focus.
'use strict';

const api = globalThis.browser ?? globalThis.chrome;
const HOST = 'org.smartworking.istituzionale';
const FASCIA_S = 15 * 60;
const PERIODO_MIN = 0.5;            // un campione ogni 30 s
const MIN_CAMPIONI = 2;             // un sito conta nella fascia con almeno 2 campioni (1 minuto)
const INATTIVO_S = 120;             // oltre 2 minuti senza input l'utente non è «attivo»
const CONFIG_TTL_MS = 5 * 1000;    // ≤5 s: dopo Pausa/Chiudi flush della fascia parziale prima dell'aggregazione (ALFA B12)
// (e subito se l'host risponde raccolta:false / raccolta_non_attiva su una fascia)
const RE_ID = /^[a-z0-9_]{1,32}$/;

async function leggiStore() {
  return await api.storage.local.get({
    fascia: null, conteggi: {}, perche: {}, coda: [], cfg: null, cfgTs: 0,
  });
}

async function nativo(msg) {
  return await api.runtime.sendNativeMessage(HOST, msg);
}

// {siti: {id: [domini]}, esclusi: [domini], raccolta: bool}; senza host: nessuna raccolta
async function configurazione(st) {
  if (st.cfg && Date.now() - st.cfgTs < CONFIG_TTL_MS) return st.cfg;
  try {
    const r = await nativo({ cmd: 'config' });
    if (r && r.ok && r.siti) {
      st.cfg = { siti: r.siti, esclusi: r.esclusi || [], raccolta: r.raccolta === true };
      st.cfgTs = Date.now();
      return st.cfg;
    }
  } catch (_) { /* host assente */ }
  return { siti: {}, esclusi: [], raccolta: false };
}

function corrisponde(h, d) { return h === d || h.endsWith('.' + d); }

// Solo id di siti in elenco; fuori elenco / esclusi → null (non «web_generico»).
function classifica(nomeHost, cfg) {
  const h = String(nomeHost || '').toLowerCase();
  if (!h || (cfg.esclusi || []).some(d => corrisponde(h, d))) return null;
  for (const [id, domini] of Object.entries(cfg.siti || {})) {
    if (RE_ID.test(id) && domini.some(d => corrisponde(h, d))) return id;
  }
  return null;
}

// {id} se la finestra ha il focus, l'utente è attivo e la scheda è un sito in elenco; altrimenti {perche}.
async function campione(cfg) {
  const w = await api.windows.getLastFocused({ populate: true });
  if (!w || !w.focused || w.type !== 'normal') return { perche: 'senza_focus' };
  if ((await api.idle.queryState(INATTIVO_S)) !== 'active') return { perche: 'inattivo' };
  const scheda = (w.tabs || []).find(t => t.active);
  if (!scheda) return { perche: 'senza_scheda' };
  if (!scheda.url) return { perche: 'url_non_visibile' };   // fuori elenco o pagina interna: non distinguibili
  let u;
  try { u = new URL(scheda.url); } catch (_) { return { perche: 'url_non_valido' }; }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return { perche: 'pagina_interna' };
  const id = classifica(u.hostname, cfg);
  return id ? { id } : { perche: 'url_non_visibile' };      // hostname fuori elenco (raro: host_permissions)
}

// Aggiorna cfg.raccolta dalla risposta dell'host (presente su ogni messaggio).
function applicaRaccolta(st, r) {
  if (!r || typeof r.raccolta !== 'boolean') {
    if (r && r.rifiutato === 'raccolta_non_attiva') {
      if (!st.cfg) st.cfg = { siti: {}, esclusi: [], raccolta: false };
      st.cfg.raccolta = false;
      st.cfgTs = Date.now();
    }
    return;
  }
  if (!st.cfg) st.cfg = { siti: {}, esclusi: [], raccolta: r.raccolta };
  else st.cfg.raccolta = r.raccolta;
  st.cfgTs = Date.now();
}

async function svuotaCoda(st) {
  while (st.coda.length) {
    const f = st.coda[0];
    const msg = { cmd: 'fascia', ts: f.ts, sito: f.sito, campioni: f.n };
    if (f.parziale) msg.parziale = true;
    const r = await nativo(msg);
    if (!r || (!r.ok && !r.rifiutato)) throw new Error('host');
    applicaRaccolta(st, r);
    st.coda.shift();
    // Pausa/stop: non campionare oltre in questo passo (i messaggi in coda restano per il prossimo tick)
    if (st.cfg && st.cfg.raccolta === false) return;
  }
}

let catena = Promise.resolve();
function passo() { catena = catena.then(eseguiPasso, eseguiPasso); return catena; }

function accodaFasciaCorrente(st, { parziale = false } = {}) {
  if (st.fascia === null) return;
  for (const [sito, n] of Object.entries(st.conteggi)) {
    if (n >= MIN_CAMPIONI && RE_ID.test(sito) && sito !== 'web_generico') {
      const msg = { ts: st.fascia, sito, n };
      if (parziale) msg.parziale = true;   // Chiudi/Pausa: host accetta la fascia ancora aperta
      st.coda.push(msg);
    }
  }
  st.coda = st.coda.slice(-200);
  st.conteggi = {}; st.perche = {};
}

async function eseguiPasso() {
  const st = await leggiStore();
  const raccoltaPrima = !!(st.cfg && st.cfg.raccolta);
  let cfg = await configurazione(st);
  // Collaudo ALFA B12: a Chiudi/Pausa (raccolta true→false) invia subito la fascia parziale in corso
  if (raccoltaPrima && cfg.raccolta === false) {
    accodaFasciaCorrente(st, { parziale: true });
  }
  const ora = Math.floor(Date.now() / 1000);
  const fascia = ora - (ora % FASCIA_S);
  if (st.fascia !== null && st.fascia < fascia) {
    accodaFasciaCorrente(st, { parziale: false });
    st.fascia = fascia;
  }
  if (st.fascia === null) st.fascia = fascia;
  // Prima la coda: se l'host dice raccolta:false / raccolta_non_attiva, i campioni si fermano subito
  try { await svuotaCoda(st); } catch (_) { /* si riprova al prossimo passo */ }
  cfg = st.cfg || cfg;
  if (cfg.raccolta) {
    let r = { perche: 'errore_api' };
    try { r = await campione(cfg); } catch (_) { r = { perche: 'errore_api' }; }
    if (r.id) st.conteggi[r.id] = (st.conteggi[r.id] || 0) + 1;
    else if (r.perche) st.perche[r.perche] = (st.perche[r.perche] || 0) + 1;
  }
  await api.storage.local.set({
    fascia: st.fascia, conteggi: st.conteggi, perche: st.perche, coda: st.coda, cfg: st.cfg, cfgTs: st.cfgTs,
  });
}

async function assicuraAllarme() {
  if (!(await api.alarms.get('passo'))) {
    api.alarms.create('passo', { delayInMinutes: 0.1, periodInMinutes: PERIODO_MIN });
  }
}

api.alarms.onAlarm.addListener(a => { if (a.name === 'passo') passo(); });
api.runtime.onInstalled.addListener(assicuraAllarme);
api.runtime.onStartup.addListener(() => { assicuraAllarme(); passo(); });
assicuraAllarme();

if (typeof module !== 'undefined') {
  module.exports = { classifica, campione, eseguiPasso, configurazione, applicaRaccolta, accodaFasciaCorrente, CONFIG_TTL_MS };
}
