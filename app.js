/* The Shabaqo Stone — viewer ("quiet" variant: same viewer, lighter chrome).
 * Deep-zoom photo/relief surfaces (OpenSeadragon) with a canvas ink layer drawn in
 * image coordinates. Data: data/stone.json (built by scripts/build_data.py).
 */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const STATUS_LABEL = {
    confirmed: "confirmed",
    corrected: "corrected vs. Breasted 1901",
    added: "added (not in Breasted 1901)",
    not_visible: "not visible on the stone",
    uncertain: "uncertain",
  };
  // the Egyptological yod (U+A7BC/D) is missing from most fonts: show it as i/I with hook above
  const tl = t => (t || "").replace(/\uA7BD/g, "\u1EC9").replace(/\uA7BC/g, "\u1EC8");
  const COLORS = {
    // faience on basalt (style.css): faience, carnelian, amethyst, slate, gypsum
    confirmed: "#9fe2d0", corrected: "#f2937e", added: "#d7c2ff",
    not_visible: "#8fa6b8", uncertain: "#f3eee4",
  };

  const store = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch { return null; } };

  let D, viewer, canvas, ctx;
  const state = { trace: true, glyphs: false, breasted: false, roth: false, hover: null, unit: null,
                  hits: null };
  const signById = new Map(), unitById = new Map(), wordOfSign = new Map();
  let grid = null; const CELL = 256;

  // the stone's own outline, segmented from the photo (scripts/fine_outline.py); optional
  const cutout = fetch("data/stone_cutout.json").then(r => r.ok ? r.json() : null).catch(() => null);
  const shabaqo = t => t.replace(/Shabaka(?!_Stone|Stone)/g, "Shabaqo");
  const loadFailed = () => { const l = $("#loading"); l.classList.remove("done"); l.textContent = "The stone didn't load. Check the connection and reload the page."; };
  Promise.all([fetch("data/stone.json").then(r => { if (!r.ok) throw r.status; return r.text(); }).then(t => JSON.parse(shabaqo(t))), cutout])
    .then(([d, c]) => { if (c && c.length > 6) d.outline = c; init(d); }, loadFailed);

  function init(data) {
    D = data;
    for (const u of D.units) {
      unitById.set(u.id, u);
      for (const w of u.words || []) for (const s of w.signs) wordOfSign.set(s, w);
    }
    for (const s of D.signs) {
      signById.set(s.sid, s);
      s.strokePaths = (s.strokes || []).map(k => {
        const p = new Path2D(); p.moveTo(k.d[0], k.d[1]);
        for (let i = 2; i < k.d.length; i += 2) p.lineTo(k.d[i], k.d[i + 1]);
        if (k.z) p.closePath();
        return { p, w: k.w, c: k.c };
      });
    }
    D.outlinePath = new Path2D();
    if (D.outline && D.outline.length) {
      D.outlinePath.moveTo(D.outline[0], D.outline[1]);
      for (let i = 2; i < D.outline.length; i += 2) D.outlinePath.lineTo(D.outline[i], D.outline[i + 1]);
      D.outlinePath.closePath();
    }
    D.geo = D.signs.filter(s => s.box);
    buildGrid();
    setupViewer();
    document.fonts.load("40px 'Noto Sans Egyptian Hieroglyphs'", "\u{13000}").then(() => { metricCache.clear(); fontVer++; draw(); });
    buildMap();
    buildAbout();
    wireUI();
  }

  // Breasted's copy is ~9000 polygons / 117k points: split it into spatial chunks (holes stay with
  // the outline that contains them, for the even-odd fill) so a frame fills only the chunks in view.
  function chunkPolys(polys, CELLSZ = 1024) {
    const items = polys.map(poly => {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i < poly.length; i += 2) {
        x0 = Math.min(x0, poly[i]); x1 = Math.max(x1, poly[i]); y0 = Math.min(y0, poly[i + 1]); y1 = Math.max(y1, poly[i + 1]);
      }
      return { poly, b: [x0, y0, x1, y1], a: (x1 - x0) * (y1 - y0) };
    }).sort((p, q) => q.a - p.a);
    const chunks = new Map(), placed = new Map();   // cell key -> chunk; cell key -> placed outlines
    for (const it of items) {
      const [x0, y0, x1, y1] = it.b, cx = Math.floor((x0 + x1) / 2 / CELLSZ), cy = Math.floor((y0 + y1) / 2 / CELLSZ);
      let key = cx + "," + cy;
      outer: for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
        for (const o of placed.get((cx + dx) + "," + (cy + dy)) || [])
          if (o.b[0] <= x0 && o.b[1] <= y0 && o.b[2] >= x1 && o.b[3] >= y1) { key = o.key; break outer; }
      }
      let c = chunks.get(key);
      if (!c) { c = { p: new Path2D(), b: [Infinity, Infinity, -Infinity, -Infinity] }; chunks.set(key, c); }
      c.p.moveTo(it.poly[0], it.poly[1]);
      for (let i = 2; i < it.poly.length; i += 2) c.p.lineTo(it.poly[i], it.poly[i + 1]);
      c.p.closePath();
      c.b = [Math.min(c.b[0], x0), Math.min(c.b[1], y0), Math.max(c.b[2], x1), Math.max(c.b[3], y1)];
      const pk = cx + "," + cy; if (!placed.has(pk)) placed.set(pk, []); placed.get(pk).push({ b: it.b, key });
    }
    return [...chunks.values()];
  }

  const item = () => viewer.world.getItemAt(0);
  const imgToEl = (x, y) => viewer.viewport.viewportToViewerElementCoordinates(item().imageToViewportCoordinates(x, y, true));
  const elToImg = pt => item().viewportToImageCoordinates(viewer.viewport.viewerElementToViewportCoordinates(pt), true);

  /* ---------- spatial index for hit testing ---------- */
  function buildGrid() {
    grid = new Map();
    for (const s of D.geo) {
      const [x0, y0, x1, y1] = s.box;
      for (let gx = Math.floor(x0 / CELL); gx <= Math.floor(x1 / CELL); gx++)
        for (let gy = Math.floor(y0 / CELL); gy <= Math.floor(y1 / CELL); gy++) {
          const k = gx + "," + gy;
          if (!grid.has(k)) grid.set(k, []);
          grid.get(k).push(s);
        }
    }
  }
  function signAt(x, y) {
    const list = grid.get(Math.floor(x / CELL) + "," + Math.floor(y / CELL)) || [];
    let best = null, ba = Infinity;
    for (const s of list) {
      const [x0, y0, x1, y1] = s.box, p = 4;
      if (x >= x0 - p && x <= x1 + p && y >= y0 - p && y <= y1 + p) {
        const a = (x1 - x0) * (y1 - y0);
        if (a < ba) { ba = a; best = s; }
      }
    }
    return best;
  }

  /* ---------- viewer ---------- */
  function setupViewer() {
    viewer = OpenSeadragon({
      id: "viewer",
      tileSources: "tiles/photo.dzi",
      showNavigationControl: false,
      maxZoomPixelRatio: 3,
      // keep the photo filling the frame: no dragging it off the edges, no zooming out past the whole image
      // a hair over 1: OSD then also centres the photo on any axis where it is smaller than the view
      visibilityRatio: 1.0001,
      constrainDuringPan: true,
      gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
      immediateRender: false,
      blendTime: 0,
      smoothTileEdgesMinZoom: Infinity,  // skip the extra full-canvas compositing pass when zoomed in
      maxImageCacheCount: 500,           // retina screens: don't evict tiles we just showed
      ...(matchMedia("(prefers-reduced-motion: reduce)").matches ? { animationTime: 0, springStiffness: 100 } : {}),
    });
    viewer.addHandler("open-failed", () => loadFailed());
    canvas = $("#ink"); ctx = canvas.getContext("2d");
    const ro = new ResizeObserver(sizeCanvas); ro.observe($("#viewer"));
    viewer.addHandler("open", () => {
      syncPanelMargin(true);
      lockMinZoom();
      const fit = D.home;
      if (fit) viewer.viewport.fitBoundsWithConstraints(rectFromImage(fit), true);
      draw();
    });
    viewer.addOnceHandler("tile-loaded", () => setTimeout(() => $("#loading").classList.add("done"), 250));
    viewer.addHandler("resize", () => { syncPanelMargin(true); lockMinZoom(); viewer.viewport.applyConstraints(true); });
    viewer.addHandler("animation-start", () => { moving = true; });
    viewer.addHandler("animation-finish", () => { moving = false; draw(); });
    // OSD raises this right after drawing the photo, in the same frame: draw the ink now, not a frame later
    viewer.addHandler("update-viewport", renderNow);

    new OpenSeadragon.MouseTracker({
      element: viewer.canvas,
      moveHandler: e => onMove(e.position),
      leaveHandler: () => { state.hover = null; $("#tip").hidden = true; draw(); },
    });
    viewer.addHandler("canvas-click", e => {
      if (!e.quick) return;
      const s = hitAt(e.position);
      if (s) { hideTip(); openUnit(s.unit, s.sid); }
    });
  }
  // Smallest zoom = the whole photo fitted into the frame (OSD centres it if the frame's aspect differs).
  // While the reading panel is open, the strip it covers is outside the view as far as fitting and the
  // edge clamp are concerned, so a column at the stone's right edge can still be brought out beside it.
  function syncPanelMargin(immediately) {
    if (!viewer || !viewer.viewport) return;
    // the name/find strip on top and the switches/map underneath float over the wall: keep the stone between them
    const vw = $("#viewer").clientWidth, vh = $("#viewer").clientHeight, p = $("#panel");
    const side = !p.hidden && p.offsetWidth < vw * 0.8, under = !p.hidden && !side;
    const m = { top: Math.round($("#top").offsetHeight * 0.8), right: side ? p.offsetWidth : 0,
                bottom: under ? Math.round(vh - p.offsetTop) : Math.round($("#foot").offsetHeight * 0.85), left: 0 };
    const o = viewer.viewport.getMargins();
    if (o.top === m.top && o.right === m.right && o.bottom === m.bottom) return;
    viewer.viewport.setMargins(m);
    lockMinZoom();
    viewer.viewport.applyConstraints(immediately);
  }
  function lockMinZoom() {
    const vp = viewer.viewport, saved = vp.homeFillsViewer;
    vp.homeFillsViewer = false;
    vp.minZoomLevel = vp.getHomeZoom();
    vp.homeFillsViewer = saved;
  }
  // The ink canvas is the view plus a margin of PAD view-widths on each side (snapped to whole device px;
  // capped to stay under 16 Mpx, Safari's canvas limit). It is placed with a CSS transform, so while the view
  // moves the compositor just moves and scales the last drawing (see render).
  let VW = 0, VH = 0, MX = 0, MY = 0, cssW = 0, cssH = 0;
  function sizeCanvas() {
    const r = $("#viewer").getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    cssW = r.width; cssH = r.height; VW = Math.round(r.width * dpr); VH = Math.round(r.height * dpr);
    let pad = PAD;
    while (pad > 0 && (VW * (1 + 2 * pad)) * (VH * (1 + 2 * pad)) > 16e6) pad -= 0.05;
    pad = Math.max(0, pad);
    MX = Math.round(VW * pad); MY = Math.round(VH * pad);
    canvas.width = VW + 2 * MX; canvas.height = VH + 2 * MY;
    canvas.style.width = canvas.width / dpr + "px"; canvas.style.height = canvas.height / dpr + "px";
    frame = null; cache = null;
    draw();
  }
  function rectFromImage([x0, y0, x1, y1]) {
    return item().imageToViewportRectangle(x0, y0, x1 - x0, y1 - y0);
  }
  function hitAt(pos) {
    const p = elToImg(pos);
    return signAt(p.x, p.y);
  }

  /* ---------- drawing ----------
   * The ink is drawn at the exact current view on every OSD frame, synchronously in OSD's own
   * 'update-viewport' (fired right after it draws the photo), so the tracing never lags a frame
   * behind the photo. At rest it is always drawn exactly (stroke widths have screen-px minimums, so a
   * scaled bitmap would be slightly too thick or thin); while the view moves, the last exact render is
   * reused, moved and scaled within MOTION_TOL, and redrawn exactly once the view is still (SETTLE_MS).
   * The rendered layers are kept as `under` (Breasted's and Rothöhler's copies) and `signs`, so a
   * hover with the view at rest only recomposites them and draws the focused word on top.
   */
  let raf = 0, moving = false, hitsVer = 0, fontVer = 0;
  let cache = null;                 // { key, x0, y0, x1, y1, k, under, signs }
  let frame = null;                 // what the ink canvas shows: { ckey, x0, y0, k } (canvas px = (image - x0) * k)
  const MOTION_TOL = 1.12, SETTLE_MS = 140, PAD = 0.2;   // motion reuse: scale range, settle delay, render margin
  let lastView = null, lastChange = 0, settleT = 0;
  function draw() { if (!raf) raf = requestAnimationFrame(render); }
  const perf = { on: false, t: [] };   // SS.perf.on = true to record ink frame times (ms)
  function renderNow() {
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    if (!perf.on) return render();
    const t0 = performance.now(); render(); perf.t.push(performance.now() - t0);
  }
  const baseKey = () => [state.trace, state.glyphs, state.breasted, state.roth, copyVer, state.unit, hitsVer, fontVer,
                         VW, VH].join("|");
  function view() {
    const o = imgToEl(0, 0), q = imgToEl(1000, 0), sc = (q.x - o.x) / 1000;
    const dpr = window.devicePixelRatio || 1, W = cssW, H = cssH;
    return { o, sc, dpr, W, H, x0: -o.x / sc, y0: -o.y / sc, x1: (W - o.x) / sc, y1: (H - o.y) / sc };
  }
  function newLayer(w, h, old) {
    if (old && old.width === w && old.height === h) return old;
    const c = document.createElement("canvas"); c.width = w; c.height = h; return c;
  }
  function render() {
    raf = 0;
    if (!viewer || !viewer.world.getItemAt(0) || !canvas.width) return;
    const v = view(), key = baseKey(), k = v.sc * v.dpr, now = performance.now();
    if (!lastView || lastView.k !== k || lastView.x0 !== v.x0 || lastView.y0 !== v.y0) { lastChange = now; lastView = { k, x0: v.x0, y0: v.y0 }; }
    const inMotion = moving || now - lastChange < SETTLE_MS;
    const lodMode = k <= LOD_K;   // zoomed out: the ink comes from the whole-stone bitmap
    const ckey = key + "|" + (lodMode ? "L" : "C") + "|" + (state.hover ? state.hover.sid : "");
    // Is the current drawing still good? Exactly (at rest: same scale, on the device-pixel grid), or, while
    // the view moves, near enough (scale within MOTION_TOL, view inside the margin) to be moved and scaled by
    // the compositor until the view settles. Either way the canvas itself is not touched.
    if (frame && frame.ckey === ckey) {
      const r = k / frame.k, tx = (v.o.x + frame.x0 * v.sc) * v.dpr, ty = (v.o.y + frame.y0 * v.sc) * v.dpr;
      const inside = v.x0 >= frame.x0 && v.y0 >= frame.y0 &&
                     v.x1 <= frame.x0 + canvas.width / frame.k && v.y1 <= frame.y0 + canvas.height / frame.k;
      const aligned = Math.abs(r - 1) < 1e-9 && Math.abs(tx - Math.round(tx)) < 0.01 && Math.abs(ty - Math.round(ty)) < 0.01;
      if (inside && (aligned || (inMotion && r > 1 / MOTION_TOL && r < MOTION_TOL))) {
        place(tx / v.dpr, ty / v.dpr, r);
        if (!aligned) { clearTimeout(settleT); settleT = setTimeout(draw, SETTLE_MS); }
        return;
      }
    }
    composite(v, key, ckey, lodMode);
  }
  let placed = "";
  function place(tx, ty, r) {
    const t = `matrix(${r}, 0, 0, ${r}, ${tx}, ${ty})`;
    if (t !== placed) { canvas.style.transform = t; placed = t; }
  }
  // draw the ink canvas for the view as it is now: backdrop, layers, the hovered word on top
  function composite(v, key, ckey, lodMode) {
    const k = v.sc * v.dpr;
    let f, blit;
    if (lodMode) {
      const layers = lodLayers(v.dpr);
      f = { x0: v.x0 - MX / k, y0: v.y0 - MY / k, k, layers };
      // pick the mip level just above the current scale: the blit then shrinks by at most 2x,
      // which plain bilinear filtering handles without shimmer
      const lvl = Math.max(0, Math.floor(Math.log2(LOD_K / k)));
      const dx = -f.x0 * k, dy = -f.y0 * k;
      blit = (c, a) => {
        if (!c) return;
        const m = lodMip(c, lvl), s = (2 ** lvl / LOD_K) * k;   // mip px -> device px
        ctx.globalAlpha = a; ctx.drawImage(m, dx, dy, m.width * s, m.height * s);
      };
    } else {
      // reuse the exact layers if the view sits on their pixel grid (a hover at rest), else render them anew
      const ox = cache ? (cache.x0 - v.x0) * k : 0, oy = cache ? (cache.y0 - v.y0) * k : 0;
      const reuse = cache && cache.key === key && cache.k === k && v.x0 >= cache.x0 && v.y0 >= cache.y0 &&
                    v.x1 <= cache.x1 && v.y1 <= cache.y1 && Math.abs(ox - Math.round(ox)) < 0.01 && Math.abs(oy - Math.round(oy)) < 0.01;
      if (!reuse) renderCache(v, key);
      f = { x0: cache.x0, y0: cache.y0, k, layers: cache };
      blit = (c, a) => { if (!c) return; ctx.globalAlpha = a; ctx.drawImage(c, 0, 0); };
    }
    f.ckey = ckey; frame = f;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const px = 1 / v.sc, T = () => ctx.setTransform(k, 0, 0, k, -f.x0 * k, -f.y0 * k);
    T(); drawBackdrop(f, px);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "low";
    blit(f.layers.under, 1);

    const focus = new Set();
    if (state.hover) {
      const w = wordOfSign.get(state.hover.sid);
      (w ? w.signs : [state.hover.sid]).forEach(id => focus.add(id));
    }
    // dim the rest of the stone while a word is focused (unless a column or search already sets the emphasis)
    blit(f.layers.signs, focus.size && !state.unit && !state.hits ? 0.35 : 1);
    ctx.globalAlpha = 1;

    T();
    for (const id of focus) { const s = signById.get(id); if (s && s.box) drawSign(s, COLORS[s.status], 1, px, true, true); }
    if (state.hover && state.hover.box) {
      // corner brackets, like an epigrapher's marks, rather than a box
      const g = 5 * px, [x0, y0, x1, y1] = state.hover.box.map((v, i) => v + (i < 2 ? -g : g));
      const t = Math.min(12 * px, (x1 - x0) / 3, (y1 - y0) / 3);
      ctx.strokeStyle = "rgba(235, 227, 211, .85)";
      ctx.lineWidth = 1.4 * px; ctx.lineCap = "round"; ctx.beginPath();
      ctx.moveTo(x0, y0 + t); ctx.lineTo(x0, y0); ctx.lineTo(x0 + t, y0);
      ctx.moveTo(x1 - t, y0); ctx.lineTo(x1, y0); ctx.lineTo(x1, y0 + t);
      ctx.moveTo(x1, y1 - t); ctx.lineTo(x1, y1); ctx.lineTo(x1 - t, y1);
      ctx.moveTo(x0 + t, y1); ctx.lineTo(x0, y1); ctx.lineTo(x0, y1 - t);
      ctx.stroke();
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    place((v.o.x + f.x0 * v.sc), (v.o.y + f.y0 * v.sc), 1);
  }
  // Cut the stone out of its gallery photo: paint everything outside the outline in the page's
  // backdrop colour (same frame as the photo, so it can't lag), with a soft rim just outside the edge.
  let backdropColor = null;
  function drawBackdrop(f, px) {
    if (!D.outline || D.outline.length < 6) return;
    if (!backdropColor) backdropColor = getComputedStyle(document.documentElement).getPropertyValue("--backdrop").trim() || "#2b2824";
    const m = 40 * px, x1 = f.x0 + canvas.width / f.k, y1 = f.y0 + canvas.height / f.k;
    const outside = new Path2D();
    outside.rect(f.x0 - m, f.y0 - m, x1 - f.x0 + 2 * m, y1 - f.y0 + 2 * m);
    outside.addPath(D.outlinePath);
    ctx.fillStyle = backdropColor; ctx.fill(outside, "evenodd");
    ctx.save(); ctx.clip(outside, "evenodd"); ctx.lineJoin = "round";
    for (const [w, a] of [[26, 0.10], [14, 0.16], [6, 0.28]]) {
      ctx.strokeStyle = `rgba(0, 0, 0, ${a})`; ctx.lineWidth = w * px; ctx.stroke(D.outlinePath);
    }
    ctx.restore();
  }
  /* Level of detail. Below LOD_K device px per image px, the ink is drawn from one bitmap of the whole
   * photo rendered at LOD_K, with every screen-px minimum (line widths, halo, ticks) fixed at its value
   * at that zoom, i.e. in image units. Scaling that bitmap is then exactly what direct drawing with
   * those widths would give (lines thin as you zoom out, like ink on a drawing, no snapping), and at
   * LOD_K itself both paths give the same widths, so the hand-over is invisible. 0.43 keeps the bitmap
   * under 16 Mpx (Safari's canvas limit).
   */
  const LOD_K = 0.43;
  let lod = null;   // { key, under, signs }
  function lodLayers(dpr) {
    const key = [state.trace, state.glyphs, state.breasted, state.roth, copyVer, state.unit, hitsVer, fontVer, dpr].join("|");
    if (lod && lod.key === key) return lod;
    const W = Math.ceil(D.image.w * LOD_K), H = Math.ceil(D.image.h * LOD_K);
    const needUnder = (state.breasted && D.breastedChunks) || (state.roth && D.rothChunks);
    const under = needUnder ? newLayer(W, H, lod && lod.under) : null;
    const signs = newLayer(W, H, lod && lod.signs);
    lod = { key, under, signs };
    const px = dpr / LOD_K, tl = { x: 0, y: 0 }, br = { x: D.image.w, y: D.image.h }, prev = ctx;
    try {
      for (const [c, fn] of [[under, renderUnder], [signs, renderSigns]]) {
        if (!c) continue;
        ctx = c.getContext("2d");
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, W, H);
        ctx.setTransform(LOD_K, 0, 0, LOD_K, 0, 0);
        fn(px, tl, br);
      }
    } finally { ctx = prev; }
    return lod;
  }
  // half-size copies of a LOD layer, made once (high-quality filtering) and kept on the canvas object
  function lodMip(c, lvl) {
    const mips = c._mips && c._mipsKey === lod.key ? c._mips : (c._mipsKey = lod.key, c._mips = [c]);
    while (mips.length <= lvl) {
      const src = mips[mips.length - 1];
      if (src.width < 64) break;
      const m = document.createElement("canvas");
      m.width = Math.ceil(src.width / 2); m.height = Math.ceil(src.height / 2);
      const g = m.getContext("2d"); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
      g.drawImage(src, 0, 0, src.width / 2, src.height / 2);
      mips.push(m);
    }
    return mips[Math.min(lvl, mips.length - 1)];
  }
  function renderCache(v, key) {
    const k = v.sc * v.dpr;                        // device px per image unit
    // the same area as the ink canvas (view + margin), so short pans and the MOTION_TOL zoom range reuse it
    const x0 = v.x0 - MX / k, y0 = v.y0 - MY / k;
    const w = canvas.width, h = canvas.height;
    const x1 = x0 + w / k, y1 = y0 + h / k;
    const needUnder = (state.breasted && D.breastedChunks) || (state.roth && D.rothChunks);
    const under = needUnder ? newLayer(w, h, cache && cache.under) : null;
    const signs = newLayer(w, h, cache && cache.signs);
    cache = { key, x0, y0, x1, y1, k, under, signs };
    const prev = ctx;
    try {
      if (under) {
        ctx = under.getContext("2d");
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, w, h);
        ctx.setTransform(k, 0, 0, k, -x0 * k, -y0 * k);
        renderUnder(1 / v.sc, { x: x0, y: y0 }, { x: x1, y: y1 });
      }
      ctx = signs.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, w, h);
      ctx.setTransform(k, 0, 0, k, -x0 * k, -y0 * k);
      renderSigns(1 / v.sc, { x: x0, y: y0 }, { x: x1, y: y1 });
    } finally { ctx = prev; }
  }
  // per-sign emphasis: the open column and search hits at full strength, the rest dimmed
  function signAlpha(s) {
    const unitSel = state.unit, hits = state.hits, dim = hits ? 0.35 : 1;
    let a = (unitSel && s.unit === unitSel) ? 1 : dim * (unitSel ? 0.6 : 1);
    if (hits && hits.has(s.sid)) a = 1;
    return a;
  }
  /* Batched traces. Drawing ~4400 strokes one by one (halo + ink, each with its own state changes) was the
   * cost of every zoomed-in frame. Strokes that look the same (colour, confidence, width class, emphasis)
   * are merged into one Path2D per spatial chunk, so a frame strokes a few dozen paths per visible chunk.
   * Widths are bucketed to 0.25 image px; the screen-px minimum is still applied per frame. Rebuilt only
   * when the emphasis changes (column opened, search hits). Glyphs, untraced corner ticks and the hovered
   * word keep the per-sign drawing. */
  const INK_CELL = 1024;
  let ink = null;   // { key, chunks: [{ b, groups: [{ p, col, ca, w, a, dash }] }], untraced: [sign] }
  function inkBatches() {
    const key = [state.unit, hitsVer].join("|");
    if (ink && ink.key === key) return ink;
    const cells = new Map(), untraced = [];
    for (const s of D.geo) {
      if (!s.strokePaths.length) { untraced.push(s); continue; }
      const [x0, y0, x1, y1] = s.box, ck = Math.floor((x0 + x1) / 2 / INK_CELL) + "," + Math.floor((y0 + y1) / 2 / INK_CELL);
      let c = cells.get(ck);
      if (!c) { c = { b: [Infinity, Infinity, -Infinity, -Infinity], g: new Map() }; cells.set(ck, c); }
      c.b = [Math.min(c.b[0], x0), Math.min(c.b[1], y0), Math.max(c.b[2], x1), Math.max(c.b[3], y1)];
      const col = COLORS[s.status] || COLORS.confirmed, a = signAlpha(s);
      for (const k of s.strokePaths) {
        const w = Math.round(k.w * 4) / 4, gk = col + "|" + k.c + "|" + w + "|" + a;
        let g = c.g.get(gk);
        if (!g) {
          g = { p: new Path2D(), col, w, a, ca: k.c === "c" ? 1 : k.c === "f" ? 0.65 : 0.5, dash: k.c === "r" };
          c.g.set(gk, g);
        }
        g.p.addPath(k.p);
      }
    }
    ink = { key, chunks: [...cells.values()].map(c => ({ b: c.b, groups: [...c.g.values()] })), untraced };
    return ink;
  }
  function renderSigns(px, tl, br) {
    if (!(state.trace || state.glyphs)) return;
    const vis = b => b[2] > tl.x && b[0] < br.x && b[3] > tl.y && b[1] < br.y;
    const onDark = true;
    if (state.trace) {
      const B = inkBatches(), minW = 1.6 * px;
      const chunks = B.chunks.filter(c => vis(c.b));
      ctx.lineCap = "round"; ctx.lineJoin = "round";
      // all halos first, then all ink, so no halo ever covers a neighbour's ink
      for (const pass of ["halo", "ink"]) {
        if (pass === "halo") ctx.strokeStyle = "#140e08";
        for (const c of chunks) for (const g of c.groups) {
          const lw = Math.max(g.w, minW);
          if (g.dash) ctx.setLineDash([lw * 1.2, lw * 1.6]);
          if (pass === "halo") { ctx.globalAlpha = g.a * g.ca * 0.55; ctx.lineWidth = lw + 2.4 * px; }
          else { ctx.globalAlpha = g.a * g.ca * 0.95; ctx.strokeStyle = g.col; ctx.lineWidth = lw; }
          ctx.stroke(g.p);
          if (g.dash) ctx.setLineDash([]);
        }
      }
      ctx.globalAlpha = 1;
      // untraced signs: corner ticks, per sign (few)
      for (const s of B.untraced) if (vis(s.box)) drawSign(s, COLORS[s.status] || COLORS.confirmed, signAlpha(s), px, false, onDark);
    }
    if (state.glyphs)
      for (const s of D.geo) if (vis(s.box)) drawGlyph(s, COLORS[s.status] || COLORS.confirmed, signAlpha(s) * (state.trace ? 0.35 : 0.9));
  }


  function renderUnder(px, tl, br) {
    const fill = (chunks, col) => {
      ctx.fillStyle = col;
      for (const c of chunks)
        if (c.b[2] > tl.x && c.b[0] < br.x && c.b[3] > tl.y && c.b[1] < br.y) ctx.fill(c.p, "evenodd");
    };
    if (state.breasted && D.breastedChunks) fill(D.breastedChunks, "rgba(235, 72, 58, .6)");
    if (state.roth && D.rothChunks) fill(D.rothChunks, "rgba(70, 110, 255, .62)");
  }
  // Sign forms come from the hieroglyph font, mirrored: the stone's text is
  // retrograde, so its signs face right while Unicode's face left.
  const metricCache = new Map();
  function glyphMetrics(ch) {
    if (!metricCache.has(ch)) {
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.font = "100px 'Noto Sans Egyptian Hieroglyphs'";
      const m = ctx.measureText(ch);
      ctx.restore();
      const w = m.actualBoundingBoxLeft + m.actualBoundingBoxRight;
      const h = m.actualBoundingBoxAscent + m.actualBoundingBoxDescent;
      if (!(w > 0 && h > 0)) return null;  // font not ready yet; don't cache
      metricCache.set(ch, { w, h, l: m.actualBoundingBoxLeft, a: m.actualBoundingBoxAscent });
    }
    return metricCache.get(ch);
  }
  function drawGlyph(s, col, alpha) {
    const g = s.uni && glyphMetrics(s.uni);
    if (!g) return false;
    const [x0, y0, x1, y1] = s.box, bw = x1 - x0, bh = y1 - y0;
    const f = Math.min(bw / g.w, bh / g.h) * 100 * 0.96;
    const k = f / 100, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    ctx.save();
    ctx.translate(cx, cy); if (s.mirror !== false) ctx.scale(-1, 1);
    ctx.font = `${f}px 'Noto Sans Egyptian Hieroglyphs'`;
    ctx.fillStyle = col; ctx.globalAlpha = alpha;
    ctx.fillText(s.uni, -g.w * k / 2 + g.l * k, -g.h * k / 2 + g.a * k);
    ctx.restore();
    return true;
  }
  function drawSign(s, col, alpha, px, glow, onDark) {
    const [x0, y0, x1, y1] = s.box;
    if (glow) { ctx.shadowColor = col; ctx.shadowBlur = 12; }
    if (state.trace) {
      if (s.strokePaths.length) {
        // the stone's own strokes: groove centre lines at their measured width
        ctx.lineCap = "round"; ctx.lineJoin = "round";
        const ink = col;
        for (const k of s.strokePaths) {
          const a = k.c === "c" ? 1 : k.c === "f" ? 0.65 : 0.5;
          const lw = Math.max(k.w, 1.6 * px);
          if (k.c === "r") ctx.setLineDash([lw * 1.2, lw * 1.6]);
          // dark halo so the colour reads on bright and dark stone alike
          ctx.globalAlpha = alpha * a * 0.55; ctx.strokeStyle = "#140e08"; ctx.lineWidth = lw + 2.4 * px; ctx.stroke(k.p);
          ctx.globalAlpha = alpha * a * (glow ? 1 : 0.95); ctx.strokeStyle = ink; ctx.lineWidth = lw; ctx.stroke(k.p);
          if (k.c === "r") ctx.setLineDash([]);
        }
      } else {
        // not traced yet: corner ticks only, so the sign is findable without inventing a shape
        const t = Math.min(10 * px, (x1 - x0) / 3, (y1 - y0) / 3);
        ctx.globalAlpha = alpha * (s.status === "not_visible" ? 0.35 : 0.6);
        ctx.strokeStyle = col; ctx.lineWidth = 1.2 * px;
        ctx.beginPath();
        ctx.moveTo(x0, y0 + t); ctx.lineTo(x0, y0); ctx.lineTo(x0 + t, y0);
        ctx.moveTo(x1 - t, y0); ctx.lineTo(x1, y0); ctx.lineTo(x1, y0 + t);
        ctx.moveTo(x1, y1 - t); ctx.lineTo(x1, y1); ctx.lineTo(x1 - t, y1);
        ctx.moveTo(x0 + t, y1); ctx.lineTo(x0, y1); ctx.lineTo(x0, y1 - t);
        ctx.stroke();
      }
    }
    if (state.glyphs) drawGlyph(s, col, alpha * (state.trace ? 0.35 : 0.9));
    ctx.shadowBlur = 0; ctx.globalAlpha = 1;
  }

  /* ---------- hover tooltip ---------- */
  function onMove(pos) {
    if (moving) return;  // no hit-testing while the view is being dragged or zoomed
    const s = hitAt(pos);
    if (s !== state.hover) { state.hover = s; draw(); }
    const tip = $("#tip");
    if (!s) { tip.hidden = true; tipFor = null; return; }
    if (s !== tipFor) { tipFor = s; fillTip(tip, s); }
    tip.hidden = false;
    hintSeen();
    const r = $("main").getBoundingClientRect();
    let x = pos.x + 18, y = pos.y + 18;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    if (x + tw > r.width - 8) x = pos.x - tw - 18;
    if (y + th > r.height - 8) y = pos.y - th - 18;
    tip.style.left = Math.max(8, x) + "px"; tip.style.top = Math.max(8, y) + "px";
  }
  // the label is rebuilt only when the pointer reaches a different sign, not on every move
  let tipFor = null;
  function hideTip() { $("#tip").hidden = true; tipFor = null; }
  function fillTip(tip, s) {
    const sg = D.signlist[s.gardiner] || { name: categoryName(s.gardiner) };
    const w = wordOfSign.get(s.sid);
    tip.style.setProperty("--pig", COLORS[s.status] || COLORS.confirmed);
    const traced = s.strokes && s.strokes.length;
    tip.innerHTML = `
      <div class="glyphrow"><div class="glyph">${s.uni || '<i class="ph"></i>'}</div>
        <dl>
          <dt>sign</dt><dd>${esc(s.gardiner)}${s.alt ? ` / ${esc(s.alt)}` : ""}${sg.name ? ` · ${esc(sg.name)}` : ""}</dd>
          ${sg.value ? `<dt>value</dt><dd><i>${esc(tl(sg.value))}</i></dd>` : ""}
          <dt>no.</dt><dd>${esc(s.sid)}${s.alias && s.alias !== s.sid ? ` <span class="dim">(1901: ${esc(s.alias)})</span>` : ""}</dd>
          <dt>status</dt><dd><span class="tag" style="--pig:${COLORS[s.status] || COLORS.confirmed}">${esc(STATUS_LABEL[s.status] || s.status)}</span>${traced || s.status === "not_visible" ? "" : ' <span class="dim">untraced</span>'}</dd>
        </dl></div>
      ${w ? `<div class="word"><span class="tr">${esc(tl(w.translit))}</span>${w.gloss ? ` · <span class="gl">${esc(w.gloss)}</span>` : ""}</div>` : ""}`;
  }

  const CATS = { A: "a man", B: "a woman", C: "a god", D: "part of the body", E: "a mammal", F: "part of a mammal",
    G: "a bird", H: "part of a bird", I: "a reptile", K: "a fish", L: "an insect", M: "a plant", N: "sky, earth or water",
    O: "a building", P: "a boat", Q: "furniture", R: "temple equipment", S: "crown or clothing", T: "a weapon",
    U: "a tool", V: "rope or basket", W: "a vessel", X: "a loaf", Y: "writing or music", Z: "a stroke", Aa: "an unclassified sign" };
  function categoryName(code) {
    const m = /^(Aa|[A-Z])/.exec(code || "");
    return m ? `unidentified (${CATS[m[1]] || "sign"})` : "unidentified";
  }

  const cap = t => t.charAt(0).toUpperCase() + t.slice(1);

  /* ---------- reading panel ---------- */
  function openUnit(id, focusSid, fly) {
    const u = unitById.get(id); if (!u) return;
    state.unit = id;
    markMap(id);
    const signs = u.signs.map(sid => signById.get(sid)).filter(Boolean);
    const idx = D.order.indexOf(id);
    const near = d => { const n = unitById.get(D.order[idx + d]); return n ? n.title.replace(/^Column/, "column").replace(/^Lines/, "lines") : ""; };
    // one row per word, in reading order; signs outside any word are grouped into rows of their own
    const words = u.words || [], rowOfWord = new Map(), rows = [];
    for (const sg of signs) {
      const wi = words.findIndex(w => w.signs.includes(sg.sid));
      if (wi >= 0) {
        if (!rowOfWord.has(wi)) { rowOfWord.set(wi, rows.length); rows.push({ w: words[wi], signs: [] }); }
        rows[rowOfWord.get(wi)].signs.push(sg);
      } else if (rows.length && !rows[rows.length - 1].w) rows[rows.length - 1].signs.push(sg);
      else rows.push({ w: null, signs: [sg] });
    }
    const glyph = sg => `<span data-sid="${sg.sid}" class="st-${sg.status}" title="${esc(sg.sid)} · ${esc(sg.gardiner)}">${sg.uni || '<i class="ph"></i>'}</span>`;
    $("#panel-body").innerHTML = `
      <h2>${esc(u.title)}</h2>
      <div class="wgrid">${rows.map((r, i) => `<div class="wr${r.w ? "" : " loose"}" data-r="${i}">
        <div class="h">${r.signs.map(glyph).join("")}</div>
        <div class="t">${r.w ? esc(tl(r.w.translit) || "…") : ""}</div><div class="g">${r.w ? esc(r.w.gloss || "") : ""}</div></div>`).join("")}</div>
      <div class="nav"><button data-go="${idx - 1}" ${idx <= 0 ? "disabled" : ""}>‹ ${esc(near(-1))}</button>
        <button data-go="${idx + 1}" ${idx >= D.order.length - 1 ? "disabled" : ""}>${esc(near(1))} ›</button></div>`;
    $("#panel").hidden = false; document.body.classList.add("panel-open");
    $$("#panel .wr").forEach(el => {
      const r = rows[+el.dataset.r], sids = r.signs.filter(x => x.box).map(x => x.sid);
      el.onmouseenter = () => { state.hover = r.signs.find(x => x.box) || null; draw(); };
      el.onmouseleave = () => { state.hover = null; draw(); };
      el.onclick = () => { const b = unionBox(sids); if (b) flyTo(b, r.w ? 2.2 : 1.6); };
    });
    $$("#panel .wr .h span").forEach(el => {
      el.onmouseenter = () => { const sg = signById.get(el.dataset.sid); if (sg && sg.box) { state.hover = sg; draw(); } };
    });
    $$("#panel .nav button").forEach(b => b.onclick = () => { const n = D.order[+b.dataset.go]; if (n) openUnit(n, null, true); });
    syncPanelMargin();
    if (fly) flyTo(u.bounds, 1.15);
    if (focusSid) { state.hover = signById.get(focusSid); }
    store("unit", id);
    draw();
  }
  function closePanel() { $("#panel").hidden = true; document.body.classList.remove("panel-open"); syncPanelMargin(); state.unit = null; markMap(null); draw(); }
  function unionBox(sids) {
    let b = null;
    for (const id of sids) { const s = signById.get(id); if (!s) continue;
      b = b ? [Math.min(b[0], s.box[0]), Math.min(b[1], s.box[1]), Math.max(b[2], s.box[2]), Math.max(b[3], s.box[3])] : [...s.box]; }
    return b;
  }
  function flyTo(box, pad = 1.2) {
    const [x0, y0, x1, y1] = box, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const w = (x1 - x0) * pad + 60, h = (y1 - y0) * pad + 60;
    // the panel's strip is a viewport margin (syncPanelMargin), so this fits into the area beside it
    viewer.viewport.fitBoundsWithConstraints(rectFromImage([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]));
  }

  /* ---------- the map: every column as a tick where it sits on the stone, as tall as what survives ---------- */
  function buildMap() {
    const cols = D.order.map(id => unitById.get(id)).filter(u => u && u.bounds && u.id !== "lines1-2");
    const X0 = Math.min(...cols.map(u => u.bounds[0])) - 40, X1 = Math.max(...cols.map(u => u.bounds[2])) + 40;
    const at = x => ((x - X0) / (X1 - X0) * 100).toFixed(2) + "%";
    const cx = u => (u.bounds[0] + u.bounds[2]) / 2;
    let html = "";
    const top = unitById.get("lines1-2");
    if (top) html += `<button class="line cell" data-u="lines1-2" style="left:${at(Math.max(X0, top.bounds[0]))};right:${(100 - parseFloat(at(Math.min(X1, top.bounds[2])))).toFixed(2)}%"
      title="${esc(top.title)}: ${esc(top.section)}" aria-label="${esc(top.title)}"></button>`;
    for (const u of cols) {
      const h = Math.round(3 + (u.preservation || 0) * 31);
      html += `<button class="tick cell" data-u="${u.id}" style="left:${at(cx(u))}" title="${esc(u.title)}${u.summary ? ": " + esc(truncate(u.summary, 160)) : ""}" aria-label="${esc(u.title)}">
        <span class="n">${esc(u.short)}</span><i style="height:${h}px"></i></button>`;
    }
    // section names underneath, each spanning the gap halfway to its neighbours
    const secs = D.sections.filter(sec => sec.units.some(id => id !== "lines1-2"));
    secs.forEach((sec, i) => {
      const us = sec.units.map(id => unitById.get(id)).filter(u => u && u.bounds);
      const prev = i ? secs[i - 1].units.map(id => unitById.get(id)).filter(Boolean).pop() : null;
      const next = i < secs.length - 1 ? unitById.get(secs[i + 1].units[0]) : null;
      const l = prev ? (cx(prev) + cx(us[0])) / 2 : X0, r = next ? (cx(us[us.length - 1]) + cx(next)) / 2 : X1;
      html += `<div class="sec" data-sec="${esc(sec.name)}" style="left:${at(l)};width:calc(${at(r)} - ${at(l)} - 6px)" title="${esc(sec.name)}: ${esc(sec.blurb || "")}"><span>${esc(sec.name)}</span></div>`;
    });
    $("#ribbon").innerHTML = html;
    $$("#ribbon [data-u]").forEach(c => {
      c.onclick = () => openUnit(c.dataset.u, null, true);
      const sec = $(`#ribbon .sec[data-sec="${CSS.escape((unitById.get(c.dataset.u) || {}).section || "")}"]`);
      if (sec) { c.onmouseenter = c.onfocus = () => sec.classList.add("peek"); c.onmouseleave = c.onblur = () => sec.classList.remove("peek"); }
    });
    fitMapLabels();
    new ResizeObserver(fitMapLabels).observe($("#ribbon"));
  }
  // a section name that doesn't fit its stretch of stone is hidden until you're on one of its columns
  function fitMapLabels() {
    const W = $("#ribbon").clientWidth;
    $$("#ribbon .sec").forEach(el => {
      const w = el.firstChild.offsetWidth;
      el.classList.toggle("tight", w > el.clientWidth + 1);
      el.classList.toggle("flip", el.offsetLeft + w > W);   // near the right edge: open leftwards
    });
  }
  function markMap(id) {
    const u = id && unitById.get(id);
    $$("#ribbon [data-u]").forEach(c => c.classList.toggle("on", c.dataset.u === id));
    $$("#ribbon .sec").forEach(c => c.classList.toggle("on", !!u && c.dataset.sec === u.section));
  }

  /* ---------- find a word ---------- */
  function runSearch(q) {
    q = q.trim().toLowerCase();
    $$("#ribbon [data-u]").forEach(c => c.classList.remove("hit"));
    if (!q) { state.hits = null; hitsVer++; $("#found").textContent = ""; draw(); return; }
    const hits = new Set(), units = new Set();
    const isCode = /^[a-z]{1,2}\d+[a-z]?$/i.test(q);
    let n = 0;
    for (const s of D.signs) if (isCode && s.gardiner.toLowerCase().replace("?", "") === q) { hits.add(s.sid); units.add(s.unit); n++; }
    for (const u of D.units) for (const w of u.words || []) {
      const hay = fold((w.translit || "") + " " + (w.gloss || ""));
      if (!isCode && hay.includes(fold(q))) { w.signs.forEach(x => hits.add(x)); units.add(u.id); n++; }
    }
    state.hits = hits; hitsVer++;
    $$("#ribbon [data-u]").forEach(c => c.classList.toggle("hit", units.has(c.dataset.u)));
    $("#found").textContent = n ? `${n} ${n === 1 ? "place" : "places"}, ${units.size} ${units.size === 1 ? "column" : "columns"}` : "not on the stone";
    draw();
  }
  // search folds case and diacritics, so "dd" finds ḏd and "iw" finds ꞽw
  function fold(t) { return tl(t).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
  function truncate(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }

  /* ---------- about (written here; stone.json's about_html predates the current viewer) ---------- */
  function buildAbout() {
    const legend = Object.entries(STATUS_LABEL).filter(([k]) => !D.stats || D.stats[k] != null)
      .map(([k, v]) => `<span class="pig" style="background:${COLORS[k]}"></span><span>${cap(v)}${D.stats ? ` (${D.stats[k]})` : ""}</span>`).join("");
    $(".about-body").innerHTML = `<h2>The Shabaqo Stone</h2>
      <p>A slab of dark stone in the British Museum (EA 498), inscribed for Shabaqo of the Twenty-fifth Dynasty
      around 710 BC. Its dedication relates that the king found a work of the ancestors eaten by worms and had it
      copied anew in stone. The text so preserved, the <i>Memphite Theology</i>, recounts Geb's judgement between
      Horus and Seth and Ptah's creation of the world through heart and tongue.</p>
      <p>The centre of the inscription is effaced by a square socket and radiating grooves, usually explained as
      later reuse as a millstone, a reading El Hawary has questioned. The king's names in line 1 were hacked out
      in antiquity.</p>
      <h3>Reading</h3>
      <p>Hover over a sign to identify it; click to open its column word by word. The strip beneath the stone maps
      the columns in place, each mark scaled to what survives. Keys: <i>t</i> trace, <i>g</i> signs,
      <i>b</i> Breasted 1901, <i>r</i> Rothöhler 2004, ← → columns, <i>/</i> search.</p>
      <h3>The trace</h3>
      <p>Each sign was traced on photographs of the stone as the centre line of its groove, at the groove's
      measured width, and checked against the stone by rendering the drawing back over it. Solid strokes are
      clearly cut, translucent ones worn, dashed ones restored. Sign numbers follow Rothöhler; the colours record
      the comparison with Breasted's copy.</p>
      <div class="legend">${legend}</div>
      <p>This is an amateur collation made with AI tracing agents, not a critical edition. The photographs share
      a single overhead light, which hides some vertical strokes. For scholarly work, see Sethe (1928),
      Rothöhler (2004) and El Hawary (2010).</p>
      <details><summary>Sources</summary><ul>
        <li>Photograph: <a href="https://commons.wikimedia.org/wiki/File:Shabaka_Stone_at_the_British_Museum.jpg">Sanjay ach</a>, Wikimedia Commons, CC BY-SA 4.0; checked against
          <a href="https://commons.wikimedia.org/wiki/File:British_Museum_2024-10-03v.jpg">2024-10-03v</a> (CC BY-SA 4.0) and
          <a href="https://commons.wikimedia.org/wiki/File:ShabakaStone-BritishMuseum-August19-08.jpg">August19-08</a> (CC BY 2.5).</li>
        <li>J. H. Breasted, “The Philosophy of a Memphite Priest”, <i>ZÄS</i> 39 (1901), 39–54, pls. I–II.</li>
        <li>B. Rothöhler, <i>Neue Gedanken zum Denkmal memphitischer Theologie</i>, Diss. Heidelberg (2004), pl. 1.</li>
        <li>S. Bryant and F. W. Read, <i>PSBA</i> 23 (1901), 160–187; K. Sethe, <i>Dramatische Texte zu altägyptischen Mysterienspielen</i> I (1928).</li>
        <li>Hieroglyphs: Noto Sans Egyptian Hieroglyphs. Viewer: OpenSeadragon.</li>
      </ul></details>`;
  }

  /* ---------- a one-time nudge for first visitors ---------- */
  function showHint() {
    if (store("seen-hint") || navigator.webdriver) return;
    const h = $("#hint");
    if (matchMedia("(hover: none)").matches) h.textContent = "Tap a sign to open its column. Pinch to look closer.";
    h.hidden = false;
    setTimeout(hintSeen, 14000);
  }
  function hintSeen() {
    const h = $("#hint"); if (h.hidden || h.classList.contains("gone")) return;
    store("seen-hint", "1"); h.classList.add("gone"); setTimeout(() => { h.hidden = true; }, 700);
  }

  /* ---------- the published copies, fetched the first time they are switched on ----------
   * Breasted's copy is inline in stone.json as built by build_data.py, or in its own file once packed
   * (scripts/pack_web_data.py); Rothöhler's is always its own file. */
  let copyVer = 0;
  const copyLoading = {};
  function loadCopy(which) {
    const chunks = which + "Chunks";
    if (D[chunks] || copyLoading[which]) return;
    if (which === "breasted" && D.breasted) { D[chunks] = chunkPolys(D.breasted); D.breasted = null; copyVer++; return; }
    const url = which === "roth" ? "data/roth_copy.json" : "data/" + ((D.lazy && D.lazy.breasted) || "breasted.json");
    copyLoading[which] = fetch(url).then(r => r.json())
      .then(j => { D[chunks] = chunkPolys(Array.isArray(j) ? j : j.polys || []); copyVer++; draw(); })
      .catch(() => { copyLoading[which] = null; });
  }

  /* ---------- UI wiring ---------- */
  function wireUI() {
    const ov = (k, v) => {
      state[k] = v ?? !state[k]; $(`#overlays [data-ov=${k}]`).classList.toggle("on", state[k]);
      if ((k === "roth" || k === "breasted") && state[k]) loadCopy(k);
      draw();
    };
    $$("#overlays button").forEach(b => b.onclick = () => ov(b.dataset.ov));
    $("#panel .close").onclick = closePanel;
    $("#search").addEventListener("input", e => runSearch(e.target.value));
    const ph = () => { $("#search").placeholder = innerWidth < 600 ? "find a word…" : "find a word: Ptah, heart, Horus…"; };
    ph(); addEventListener("resize", ph);
    $("#about-btn").onclick = () => $("#about").showModal();
    $("#about").addEventListener("click", e => { if (e.target === e.currentTarget) e.currentTarget.close(); });
    addEventListener("keydown", e => {
      if (e.target.matches("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape") closePanel();
      if (e.key === "t") ov("trace"); if (e.key === "g") ov("glyphs"); if (e.key === "b") ov("breasted"); if (e.key === "r") ov("roth");
      if (e.key === "/") { e.preventDefault(); $("#search").focus(); }
      if (state.unit && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        const i = D.order.indexOf(state.unit) + (e.key === "ArrowRight" ? 1 : -1);
        if (D.order[i]) openUnit(D.order[i], null, true);
      }
    });
    viewer.addOnceHandler("open", () => setTimeout(showHint, 1200));
  }

  /* ---------- ?bench: scripted pan/zoom, reports frame times on the page (for real hardware) ---------- */
  // the column-9 landmark: 1901 sid "9.10", or the Rothöhler sign that has it as its alias
  const benchSign = () => signById.get("9.10") || D.signs.find(s => s.alias === "9.10");
  function bench() {
    const box = document.createElement("pre");
    box.style.cssText = "position:fixed;left:12px;bottom:90px;z-index:50;margin:0;padding:10px 12px;background:rgba(10,9,8,.92);color:#ece3d2;font:12px/1.5 'JetBrains Mono',monospace;border:1px solid #3a352f;border-radius:8px;white-space:pre";
    document.body.appendChild(box);
    const vp = viewer.viewport, out = [];
    const stat = a => { a = a.slice().sort((x, y) => x - y); const q = p => a[Math.min(a.length - 1, Math.floor(p * a.length))] || 0;
      return `p50 ${q(.5).toFixed(1)}  p90 ${q(.9).toFixed(1)}  max ${q(1).toFixed(1)} ms`; };
    const phase = (label, setup, step, ms = 3000) => new Promise(res => {
      setup(); setTimeout(() => {
        const frames = []; let last = performance.now(), i = 0; perf.t = []; perf.on = true;
        const t0 = last, tick = t => { frames.push(t - last); last = t; step(i++); if (t - t0 < ms) requestAnimationFrame(tick);
          else { perf.on = false; out.push(`${label}\n  frames ${stat(frames.slice(2))}\n  ink    ${stat(perf.t)}`); box.textContent = out.join("\n"); res(); } };
        requestAnimationFrame(tick);
      }, 1500);
    });
    const center = () => vp.getCenter(true);
    box.textContent = "benchmark running… don't touch the page (about 25 s)";
    phase("whole stone · zoom in/out", () => { vp.goHome(true); },
      i => { vp.zoomBy(Math.sin(i / 15) > 0 ? 1.012 : 1 / 1.012, center(), true); vp.applyConstraints(true); })
    .then(() => phase("whole stone · zoom, Breasted on", () => { state.breasted = true; loadCopy("breasted"); vp.goHome(true); },
      i => { vp.zoomBy(Math.sin(i / 15) > 0 ? 1.012 : 1 / 1.012, center(), true); vp.applyConstraints(true); }))
    .then(() => phase("column · pan", () => { state.breasted = false; flyTo(benchSign().box, 10); },
      i => { vp.panBy(new OpenSeadragon.Point(Math.sin(i / 20) * 0.0015, 0), true); vp.applyConstraints(true); }))
    .then(() => phase("column · zoom", () => { flyTo(benchSign().box, 10); },
      i => { vp.zoomBy(Math.sin(i / 15) > 0 ? 1.015 : 1 / 1.015, center(), true); vp.applyConstraints(true); }))
    .then(() => { box.textContent += `\n\n${navigator.userAgent.match(/(Safari|Chrome|Firefox)\/[\d.]+/g)?.join(" ") || ""} · dpr ${devicePixelRatio} · ${innerWidth}×${innerHeight}`; draw(); });
  }
  if (/[?&]bench\b/.test(location.search)) addEventListener("load", () => setTimeout(() => viewer && viewer.world.getItemAt(0) ? bench() : viewer.addOnceHandler("open", () => setTimeout(bench, 1500)), 2500));

  window.SS = { flyTo: (b, p) => flyTo(b, p), openUnit, sign: id => signById.get(id), state, perf, get viewer() { return viewer; } };

  function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
})();
