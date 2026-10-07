// Test di estensione/sorgente/background.js con un'API del browser finta (Node, nessuna dipendenza).
'use strict';
const assert = require('assert');
const path = require('path');

let ora = Date.UTC(2026, 9, 5, 7, 0, 10);       // 09:00:10 ora italiana, fascia 09:00
const realeNow = Date.now;
Date.now = () => ora;

const store = {};
const inviati = [];
let raccolta = true;
let rispostaFascia = null;
let finestra = null;
let stato = 'active';
const cfg = { ok: true, raccolta: true, siti: { halley: ['gestionale.esempio.test'] }, esclusi: ['escluso.esempio.test'] };
const ascolti = {};
const evento = n => ({ addListener: f => { ascolti[n] = f; } });

globalThis.chrome = {
  storage: { local: {
    get: async def => { const o = {}; for (const k of Object.keys(def)) o[k] = k in store ? JSON.parse(JSON.stringify(store[k])) : def[k]; return o; },
    set: async o => { for (const [k, v] of Object.entries(o)) store[k] = JSON.parse(JSON.stringify(v)); },
  } },
  runtime: {
    sendNativeMessage: async (host, msg) => {
      assert.strictEqual(host, 'org.smartworking.istituzionale');
      inviati.push(msg);
      if (msg.cmd === 'config') return { ...cfg, raccolta };
      // ogni risposta porta «raccolta» (come l'host reale)
      if (rispostaFascia) return { ...rispostaFascia, raccolta: rispostaFascia.raccolta ?? raccolta };
      return { ok: true, raccolta };
    },
    onInstalled: evento('installed'), onStartup: evento('startup'),
  },
  alarms: { get: async () => null, create: () => {}, onAlarm: evento('alarm') },
  windows: { getLastFocused: async () => finestra },
  idle: { queryState: async () => stato },
};

const bg = require(path.join(__dirname, '..', '..', 'estensione', 'sorgente', 'background.js'));

function scheda(url, titolo) {
  const t = { active: true, title: titolo };
  if (url !== undefined) t.url = url;
  return { focused: true, type: 'normal', tabs: [t] };
}

(async () => {
  const c = { siti: cfg.siti, esclusi: cfg.esclusi };
  assert.strictEqual(bg.classifica('gestionale.esempio.test', c), 'halley');
  assert.strictEqual(bg.classifica('x.gestionale.esempio.test', c), 'halley');
  assert.strictEqual(bg.classifica('evilgestionale.esempio.test', c), null);
  assert.strictEqual(bg.classifica('escluso.esempio.test', { siti: { finto: ['escluso.esempio.test'] }, esclusi: ['escluso.esempio.test'] }), null);
  assert.strictEqual(bg.classifica('esempio.it', c), null);

  // senza «tabs»: scheda fuori elenco → url_non_visibile (non web_generico); aggregatore non tratta assenza come inattività
  finestra = scheda(undefined, 'Titolo segreto');
  assert.deepStrictEqual(await bg.campione(c), { perche: 'url_non_visibile' });
  finestra = scheda('https://gestionale.esempio.test/pratica/123?cf=XYZ', 'Pratica 123');
  assert.deepStrictEqual(await bg.campione(c), { id: 'halley' });
  stato = 'idle';
  assert.deepStrictEqual(await bg.campione(c), { perche: 'inattivo' });
  stato = 'active';
  finestra = { focused: false, type: 'normal', tabs: [] };
  assert.deepStrictEqual(await bg.campione(c), { perche: 'senza_focus' });

  // tre campioni halley + uno senza url: al passaggio alla 09:15 si invia solo halley; niente web_generico
  for (let i = 0; i < 3; i++) {
    finestra = scheda('https://gestionale.esempio.test/pratica/123?cf=XYZ', 'Pratica 123');
    await bg.eseguiPasso(); ora += 30000;
  }
  finestra = scheda(undefined, 'Altro');
  await bg.eseguiPasso();
  ora = Date.UTC(2026, 9, 5, 7, 15, 5);
  await bg.eseguiPasso();
  const fasce = inviati.filter(m => m.cmd === 'fascia');
  assert.deepStrictEqual(fasce, [{ cmd: 'fascia', ts: Date.UTC(2026, 9, 5, 7, 0, 0) / 1000, sito: 'halley', campioni: 3 }]);
  assert.ok(!fasce.some(m => m.sito === 'web_generico'));
  assert.strictEqual(store.perche.url_non_visibile, 1);  // campione senza url nella nuova fascia

  // nessun indirizzo, titolo o nome host nello storage o nei messaggi
  const tutto = JSON.stringify(store) + JSON.stringify(inviati.filter(m => m.cmd !== 'config'));
  for (const s of ['pratica', 'XYZ', 'Titolo', 'Pratica', 'https', 'web_generico']) assert.ok(!tutto.includes(s), s);
  assert.ok(!JSON.stringify(store.coda).includes('gestionale.esempio'));

  // raccolta non attiva (giornata non avviata o in pausa): nessun campione
  raccolta = false; store.cfg = null; store.cfgTs = 0;
  ora = Date.UTC(2026, 9, 5, 7, 20, 0);
  const prima = JSON.stringify(store.conteggi);
  finestra = scheda('https://gestionale.esempio.test/', 'x');
  await bg.eseguiPasso();
  assert.strictEqual(JSON.stringify(store.conteggi), prima);

  // cache ancora «raccolta: true», ma l'host sulla fascia dice raccolta:false → stop immediato dei campioni
  assert.ok(bg.CONFIG_TTL_MS <= 60 * 1000);
  raccolta = true;
  store.cfg = { siti: cfg.siti, esclusi: cfg.esclusi, raccolta: true };
  store.cfgTs = ora;                         // cache fresca (non scaduta)
  store.conteggi = { halley: 3 };            // abbastanza da mettere in coda al cambio fascia
  store.fascia = Date.UTC(2026, 9, 5, 7, 15, 0) / 1000;
  store.coda = [];
  store.perche = {};
  rispostaFascia = { ok: false, rifiutato: 'raccolta_non_attiva', raccolta: false };
  ora = Date.UTC(2026, 9, 5, 7, 30, 5);      // nuova fascia → flush coda → host dice stop
  finestra = scheda('https://gestionale.esempio.test/', 'x');
  const nInviati = inviati.length;
  await bg.eseguiPasso();
  assert.strictEqual(store.cfg.raccolta, false);
  assert.deepStrictEqual(store.conteggi, {}); // fascia nuova azzerata e nessun campione aggiunto
  assert.ok(inviati.slice(nInviati).some(m => m.cmd === 'fascia'));

  // passo successivo con cache «false»: ancora nessun campione anche se host non viene richiamato per config
  rispostaFascia = null; raccolta = false;
  const n2 = Object.keys(store.conteggi).length;
  await bg.eseguiPasso();
  assert.strictEqual(Object.keys(store.conteggi).length, n2);


  // Collaudo ALFA B12: passaggio raccolta true→false fa flush della fascia parziale con flag parziale
  raccolta = false;
  store.cfg = { siti: cfg.siti, esclusi: cfg.esclusi, raccolta: true };
  store.cfgTs = 0;                       // forza nuovo config → raccolta false
  store.conteggi = { halley: 4 };
  store.fascia = Math.floor(Date.UTC(2026, 9, 5, 8, 0, 0) / 1000);
  store.coda = [];
  inviati.length = 0;
  rispostaFascia = { ok: true, raccolta: false };
  ora = Date.UTC(2026, 9, 5, 8, 7, 0);    // ancora dentro la fascia 08:00
  await bg.eseguiPasso();
  const flush = inviati.filter(m => m.cmd === 'fascia');
  assert.ok(flush.length >= 1, 'atteso flush fascia parziale');
  assert.strictEqual(flush[0].parziale, true);
  assert.strictEqual(flush[0].sito, 'halley');
  assert.strictEqual(flush[0].campioni, 4);

  Date.now = realeNow;
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
