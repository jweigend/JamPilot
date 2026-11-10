// Die Webanzeige als GANZES in Node: das <script> aus index.html in einer vm,
// mit einer DOM-Attrappe, einer stellbaren Uhr und einem EventSource, dem der
// Test die Zustaende des Servers einzeln zustellt.
//
// Wozu: Die Fehler der Seite sind Zustandsfehler (Uhr, Sitzungswechsel,
// Teilzustaende). Einen ausgeschnittenen Funktionsblock sehen sie nicht, und
// String-Assertions schon gar nicht. Benutzt von tests/test_web.py
// (TestSeiteAlsGanzes); ohne Node werden diese Tests uebersprungen.
//
// Faellt ein Test hier mit `ReferenceError` oder `... is not a function` aus
// Node, fehlt meist eine DOM-Methode in der Attrappe unten - nicht etwas in
// der Seite. Die Attrappe kennt nur, was die Seite bisher benutzt.
//
//   const { seite } = require("./seite_harness.js");
//   const p = seite("/pfad/zu/index.html");
//   p.open(); p.msg({t: 2.0, committed: [...]}); p.tick(250); p.frame();
//   p.stand()  ->  {offset, now, idle, events, ...}

const fs = require("fs"), vm = require("vm");

function seite(pfad, opts = {}) {
  const html = fs.readFileSync(pfad, "utf8");
  const src = html.slice(html.indexOf("<script>") + 8, html.lastIndexOf("</script>"));

  let uhr = 1_000_000;                         // performance.now() in ms
  const elemente = new Map();
  const element = id => {
    const klassen = new Set();
    return {
      id, style: {}, dataset: {}, hidden: false, innerHTML: "", textContent: "",
      children: [], attrs: {}, clientWidth: 1000, clientHeight: 200, offsetWidth: 1,
      classList: {
        add: c => klassen.add(c), remove: c => klassen.delete(c),
        contains: c => klassen.has(c),
        toggle: (c, an) => { if (an === undefined) an = !klassen.has(c);
                             an ? klassen.add(c) : klassen.delete(c); },
      },
      get className() { return [...klassen].join(" "); },
      set className(v) { klassen.clear();
                         v.split(/\s+/).filter(Boolean).forEach(c => klassen.add(c)); },
      setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      addEventListener() {}, blur() {}, closest() { return null; },
      appendChild(c) { this.children.push(c); c.parent = this; },
      remove() { if (this.parent)
                   this.parent.children = this.parent.children.filter(x => x !== this); },
      querySelector() { return element("q"); }, querySelectorAll() { return []; },
      getContext() { return new Proxy({}, { get: () => () => {}, set: () => true }); },
      getBoundingClientRect() { return { top: 0, bottom: 50, left: 0, right: 10 }; },
    };
  };
  const $ = id => { if (!elemente.has(id)) elemente.set(id, element(id));
                    return elemente.get(id); };

  let raf = null, quelle = null;
  const speicher = new Map(Object.entries(opts.storage || {}));
  const ctx = {
    console, Math, JSON, Map, Set, Array, String, Number, Object, parseFloat,
    URLSearchParams, Infinity, NaN,
    performance: { now: () => uhr },
    document: { getElementById: $, body: $("__body"), documentElement: $("__html"),
                querySelectorAll: () => [], querySelector: () => element("q"),
                createElement: () => element("neu"), addEventListener() {},
                fullscreenElement: null },
    localStorage: { getItem: k => speicher.has(k) ? speicher.get(k) : null,
                    setItem: (k, v) => speicher.set(k, v),
                    removeItem: k => speicher.delete(k) },
    location: { search: "?k=tok" },
    requestAnimationFrame: f => { raf = f; },
    EventSource: function () { quelle = this; },
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    setTimeout: () => 1, clearTimeout() {}, setInterval() {},
    getComputedStyle: () => ({ fontSize: "20px" }),
  };
  ctx.window = { addEventListener() {}, devicePixelRatio: 1 };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  // Die `let`-Variablen der Seite sind nur aus DEMSELBEN Skript erreichbar -
  // die Auskunft wird darum angehaengt, nicht von aussen gefragt.
  vm.runInContext(src + `
    ;globalThis.__stand = () => ({ offset, shownOffset, lastT, frozenAt, epoch,
      recording, paused, link, events, now: streamNow(),
      gestoppt: typeof gestoppt === "undefined" ? null : gestoppt,
      hoerbar: hoerbaresSegment(streamNow()) });
    globalThis.__fn = { candidates, decideVoicing, renderFretboard, idleText,
                        keyCandidates, decideKeyVoicing, planKeyVoicing };
    globalThis.__instrument = setzeInstrument;
  `, ctx);

  return {
    $,
    open: () => quelle.onopen(),
    error: () => quelle.onerror(),
    msg: zustand => quelle.onmessage({ data: JSON.stringify(zustand) }),
    tick: ms => { uhr += ms; },
    frame: () => { const f = raf; f(); },
    stand: () => ({ ...ctx.__stand(), idle: $("idleTitle").textContent,
                    idleSichtbar: $("idle").style.display === "block" }),
    fn: ctx.__fn,
    instrument: ctx.__instrument,
  };
}

module.exports = { seite };
