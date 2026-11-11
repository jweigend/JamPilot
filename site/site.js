// Projektseite: drei kleine Dinge, keins davon noetig, um die Seite zu lesen.
//   1. Die Buehne im Kopf - das Laufband der Anzeige in klein, es laeuft wirklich.
//   2. Die Reiter der Instrumentenansichten.
//   3. Die Download-Knoepfe zeigen direkt auf die Dateien des neuesten Release.
// Ohne JavaScript bleibt: ein stehender Akkord, alle vier Ansichten
// untereinander und Knoepfe, die auf die Release-Seite fuehren.
"use strict";

// ---------- 1. Die Buehne ----------
(function buehne() {
  const lane = document.getElementById("stLane");
  if (!lane) return;
  const canvas = document.getElementById("stCanvas");
  const chipsEl = document.getElementById("stChips");
  const chordEl = document.getElementById("stChord");
  const degEl = document.getElementById("stDeg");
  const ctx = canvas.getContext("2d");

  // Eine Runde 1-5-6-4 in C-Dur, ein Takt je Akkord bei 120 bpm.
  const PROG = [["C", "", "1"], ["G", "", "5"], ["A", "m", "6"], ["F", "", "4"]];
  const BEAT = 0.5;            // Sekunden je Schlag
  const DUR = 4 * BEAT;        // Sekunden je Akkord
  const FENSTER = 4.3;         // so viele Sekunden Zukunft passen rechts von NOW
  const NOW = 0.14;            // Lage der NOW-Linie (Anteil der Breite, wie im CSS)

  // Synthetische Huellkurven: Anschlaege mit raschem Anstieg und Ausklang.
  // [Schlag im Takt, Hoehe]
  const BASS = [[0, 1], [1.5, 0.42], [2, 0.8], [3.5, 0.5]];
  const MIX = [[0, 0.75], [0.5, 0.3], [1, 0.95], [1.5, 0.3], [2, 0.7], [2.5, 0.3], [3, 0.95], [3.5, 0.4]];
  function huelle(muster, t, ausklang) {
    const takt = Math.floor(t / DUR);
    let e = 0;
    for (let k = takt - 1; k <= takt; k++) {
      for (const [schlag, hoehe] of muster) {
        const dt = t - (k * DUR + schlag * BEAT);
        if (dt < 0) continue;
        const v = hoehe * Math.min(dt / 0.02, 1) * Math.exp(-dt / ausklang);
        if (v > e) e = v;
      }
    }
    return e;
  }

  const name = (c) => c[0] + (c[1] ? '<span class="sfx">' + c[1] + "</span>" : "");
  const chips = new Map();     // Index des Akkords -> Element
  let aktuell = -1;

  function zeichne(t) {
    const w = lane.clientWidth, h = lane.clientHeight;
    if (!w) return;
    const nowX = w * NOW, pps = (w - nowX) / FENSTER;

    // Der grosse Akkord wechselt in dem Bild, in dem sein Chip die Linie beruehrt.
    const k0 = Math.floor(t / DUR);
    if (k0 !== aktuell) {
      const c = PROG[((k0 % PROG.length) + PROG.length) % PROG.length];
      chordEl.innerHTML = name(c);
      degEl.textContent = c[2];
      if (aktuell !== -1) {
        chordEl.classList.remove("flip");
        void chordEl.offsetWidth;
        chordEl.classList.add("flip");
      }
      aktuell = k0;
    }

    // Chips: der laufende, und alles, was ins Fenster passt.
    const bis = k0 + Math.ceil(FENSTER / DUR) + 1;
    for (let k = k0; k <= bis; k++) {
      let el = chips.get(k);
      if (!el) {
        const c = PROG[k % PROG.length];
        el = document.createElement("div");
        el.className = "chip";
        // Wie in der Anzeige: oben klein die Stufe, darunter gross der Name -
        // unter dem Namen steht nichts, dort laeuft die Huellkurve.
        el.innerHTML = '<span class="deg">' + c[2] + '</span><span class="name">'
                     + name(c) + '</span>';
        chipsEl.appendChild(el);
        chips.set(k, el);
      }
      const dt = k * DUR - t;
      const x = nowX + dt * pps;
      el.style.transform = "translateX(" + x.toFixed(1) + "px)";
      // Hinter der Linie blasst der Chip aus - er ist jetzt der grosse Akkord.
      el.style.opacity = dt >= 0 ? 1 : Math.max(0, 1 + dt / 0.35).toFixed(2);
    }
    for (const [k, el] of chips) if (k < k0) { el.remove(); chips.delete(k); }

    // Leinwand: Schlagstriche und die Huellkurve, mit derselben Uhr wie die Chips.
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const zeit = (x) => t + (x - nowX) / pps;
    const top = h * 0.49;      // bis an die Grundlinie der Akkordnamen (CSS .chip: bottom 44%)

    ctx.beginPath(); ctx.moveTo(0, h);
    for (let x = 0; x <= w; x += 2) ctx.lineTo(x, h - huelle(MIX, zeit(x), 0.1) * top * 0.8);
    ctx.lineTo(w, h); ctx.closePath();
    ctx.fillStyle = "#2b5fb84d"; ctx.fill();

    ctx.beginPath();
    for (let x = 0; x <= w; x += 2) {
      const y = h - 1 - huelle(BASS, zeit(x), 0.2) * top;
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = "#6ea8ff90"; ctx.lineWidth = 1.5; ctx.lineJoin = "round"; ctx.stroke();

    ctx.fillStyle = "#3a414a";
    const b0 = Math.ceil(zeit(0) / BEAT), b1 = Math.floor(zeit(w) / BEAT);
    for (let b = b0; b <= b1; b++) {
      const x = nowX + (b * BEAT - t) * pps;
      const eins = ((b % 4) + 4) % 4 === 0;
      ctx.fillRect(Math.round(x), h - (eins ? h * 0.13 : h * 0.06), 1, eins ? h * 0.13 : h * 0.06);
    }
  }

  // Wer keine Bewegung will, bekommt ein stehendes Bild mitten im ersten Takt.
  const ruhig = window.matchMedia("(prefers-reduced-motion: reduce)");
  let start = null, laeuft = false;
  function bild(ms) {
    if (ruhig.matches) { laeuft = false; zeichne(0.7); return; }
    if (start === null) start = ms;
    zeichne((ms - start) / 1000 + 0.7);
    requestAnimationFrame(bild);
  }
  function los() { if (!laeuft) { laeuft = true; requestAnimationFrame(bild); } }
  ruhig.addEventListener("change", los);
  window.addEventListener("resize", () => { if (ruhig.matches) zeichne(0.7); });
  los();
})();

// ---------- 2. Die Reiter ----------
(function reiter() {
  const liste = document.querySelector('[role="tablist"]');
  if (!liste) return;
  const tabs = Array.from(liste.querySelectorAll('[role="tab"]'));
  function waehle(tab, fokus) {
    for (const t of tabs) {
      const an = t === tab;
      t.setAttribute("aria-selected", an ? "true" : "false");
      t.tabIndex = an ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !an;
    }
    if (fokus) tab.focus();
  }
  liste.addEventListener("click", (ev) => {
    const tab = ev.target.closest('[role="tab"]');
    if (tab) waehle(tab, false);
  });
  liste.addEventListener("keydown", (ev) => {
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    let j = -1;
    if (ev.key === "ArrowRight") j = (i + 1) % tabs.length;
    else if (ev.key === "ArrowLeft") j = (i - 1 + tabs.length) % tabs.length;
    else if (ev.key === "Home") j = 0;
    else if (ev.key === "End") j = tabs.length - 1;
    if (j >= 0) { ev.preventDefault(); waehle(tabs[j], true); }
  });
  // Erst hier wird versteckt: ohne JavaScript stehen alle vier untereinander.
  waehle(tabs[0], false);
})();

// ---------- 3. Der Download ----------
(function download() {
  // Das eigene System hervorheben. iPhone/Android bekommen keins: dort laeuft
  // JamPilot nicht, das Telefon ist nur Anzeige.
  const ua = navigator.userAgent || "";
  let os = null;
  if (/Android|iPhone|iPad|iPod/i.test(ua)) os = null;
  else if (/Windows/i.test(ua)) os = "windows";
  else if (/Mac OS X|Macintosh/i.test(ua)) os = "macos";
  else if (/Linux|X11/i.test(ua)) os = "linux";
  if (os) {
    const karte = document.querySelector('.card[data-os="' + os + '"]');
    if (karte) karte.classList.add("yours");
    const kopf = document.getElementById("heroDownload");
    const namen = { windows: "Windows", macos: "macOS", linux: "Linux" };
    if (kopf) kopf.textContent = "Download for " + namen[os];
  }

  // Die Knoepfe fuehren auf die Release-Seite. Antwortet GitHub, zeigen sie
  // direkt auf die Datei - mit Version und Groesse. Die Dateinamen tragen die
  // Versionsnummer, darum laesst sich das nicht fest verdrahten.
  const muster = {
    windows: /windows-x86_64\.zip$/i,
    linux: /linux-x86_64\.tar\.gz$/i,
    macos: /macos-arm64\.tar\.gz$/i,
  };
  if (!window.fetch) return;
  fetch("https://api.github.com/repos/jweigend/JamPilot/releases/latest",
        { headers: { Accept: "application/vnd.github+json" } })
    .then((r) => (r.ok ? r.json() : null))
    .then((rel) => {
      if (!rel || !Array.isArray(rel.assets)) return;
      const version = String(rel.tag_name || "").replace(/^v/, "");
      for (const a of document.querySelectorAll("a[data-asset]")) {
        const datei = rel.assets.find((x) => muster[a.dataset.asset].test(x.name));
        if (!datei) continue;
        a.href = datei.browser_download_url;
        const meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = version + " · " + Math.round(datei.size / 1048576) + " MB";
        a.appendChild(meta);
      }
      const zeile = document.getElementById("relLine");
      if (zeile && version) {
        const tag = rel.published_at ? new Date(rel.published_at) : null;
        zeile.textContent = "Version " + version
          + (tag && !isNaN(tag) ? ", released " + tag.toLocaleDateString("en-GB",
              { day: "numeric", month: "long", year: "numeric" }) : "") + ".";
      }
    })
    .catch(() => {});
})();
