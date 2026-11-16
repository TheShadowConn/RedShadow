/* Hero: a live RedShadow console. A scan line sweeps the asset grid; each hit adds a finding row,
   older findings move to fixed. Rows open the real product screen in a dialog. No network calls. */
const $ = (s, r = document) => r.querySelector(s);
const hero = $('#hero');
if (hero) init();

function init() {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const win = $('.con', hero), grid = $('.con__grid', hero), rows = $('.con__rows', hero), scan = $('.con__scan', hero);
  const nOpen = $('#c-open'), nFixed = $('#c-fixed'), dlg = $('#shot-dlg'), dlgImg = $('#shot-img'), dlgCap = $('#shot-cap');
  const COLS = 12, ROWS = 8, N = COLS * ROWS;
  const SEV = { c: 'Critical', h: 'High', m: 'Medium', l: 'Low' };
  const SHOT = { c: ['17-finding-detail', 'A critical finding with CVSS score, evidence and history'], h: ['16-findings-list', 'The findings list with owners and due dates'], m: ['24-remediation-queue', 'The remediation queue of assigned findings'], l: ['20-retest-pass', 'A retest round recorded as passed'] };
  const F = [
    ['F-101', 'c', 'SQL injection in the login filter', 'auth.acme.com', 14],
    ['F-102', 'h', 'Stored XSS in support tickets', 'help.acme.com', 27],
    ['F-103', 'h', 'IDOR on invoice download', 'api.acme.com', 33],
    ['F-104', 'm', 'No rate limit on password reset', 'auth.acme.com', 40],
    ['F-105', 'c', 'Exposed admin console', '10.0.4.12', 51],
    ['F-106', 'h', 'Outdated OpenSSH on the bastion', '10.0.4.2', 58],
    ['F-107', 'm', 'Weak TLS ciphers', 'shop.acme.com', 66],
    ['F-108', 'l', 'Verbose server banner', 'cdn.acme.com', 71],
    ['F-109', 'h', 'Hard-coded API key in the mobile app', 'Acme iOS 4.2', 79],
    ['F-110', 'm', 'Open redirect after sign-in', 'shop.acme.com', 86],
    ['F-111', 'c', 'Public S3 bucket listing', 's3://acme-backups', 92],
  ].map(([id, sev, title, asset, cell]) => ({ id, sev, title, asset, cell }));

  /* grid cells (one per in-scope asset) */
  const cells = [];
  for (let i = 0; i < N; i++) { const c = document.createElement('i'); grid.appendChild(c); cells.push(c); }
  $('#c-assets').textContent = N;

  let shown = [], col = 0, open = 0, fixed = 0, timer = 0;
  const MAX = 5;

  function addRow(f, animate) {
    const li = document.createElement('li');
    const b = document.createElement('button'); b.type = 'button'; b.className = 'frow';
    const id = document.createElement('span'); id.className = 'row__id'; id.textContent = f.id;
    const sev = document.createElement('span'); sev.className = 'sev'; sev.dataset.sev = f.sev; sev.textContent = SEV[f.sev];
    const t = document.createElement('span'); t.className = 'row__t'; t.textContent = f.title;
    const a = document.createElement('span'); a.className = 'row__a'; a.textContent = f.asset;
    const st = document.createElement('span'); st.className = 'row__st'; st.textContent = 'Open';
    b.append(id, sev, t, a, st);
    b.setAttribute('aria-label', `${f.id}, ${SEV[f.sev]}: ${f.title} on ${f.asset}. Open the screen.`);
    b.addEventListener('click', () => showShot(f));
    li.appendChild(b); f.li = li; f.st = st;
    if (animate) li.classList.add('is-new');
    rows.prepend(li);
    while (rows.children.length > MAX) rows.lastElementChild.remove();
  }
  function setFixed(f) {
    if (!f || f.fixed) return; f.fixed = true; open--; fixed++;
    cells[f.cell].className = 'is-fixed';
    if (f.st) { f.st.textContent = 'Verified'; f.li.classList.add('is-fixed'); }
  }
  function count() { nOpen.textContent = open; nFixed.textContent = fixed; }

  let pause = 0;
  function step() {
    if (col >= COLS) { // finished a sweep: hold the result for a few ticks, then a new round
      if (reduce) return;
      if (++pause < 5) return;
      pause = 0; reset();
    }
    scan.style.setProperty('--col', col);
    for (let r = 0; r < ROWS; r++) {
      const i = r * COLS + col;
      const f = F.find((x) => x.cell === i && !x.found);
      if (f) {
        f.found = true; open++; cells[i].className = 'is-hit';
        addRow(f, true); shown.push(f);
        if (shown.length > 3) setFixed(shown[shown.length - 4]);
      } else if (!cells[i].className) cells[i].className = 'is-seen';
    }
    count();
    col++;
  }
  function reset() {
    col = 0; open = 0; fixed = 0; shown = [];
    F.forEach((f) => { f.found = f.fixed = false; f.li = f.st = null; });
    cells.forEach((c) => (c.className = ''));
    // keep last round's rows on screen (marked verified) until new findings push them out
    [...rows.querySelectorAll('li')].forEach((li) => { li.classList.add('is-fixed'); const s = li.querySelector('.row__st'); if (s) s.textContent = 'Verified'; });
    count();
  }

  function showShot(f) {
    const [src, alt] = SHOT[f.sev];
    const b = `assets/shots/${src}`; dlgImg.srcset = `${b}-960.webp 960w, ${b}-1920.webp 1920w, ${b}-3840.webp 3840w`; dlgImg.src = `${b}-1920.webp`; dlgImg.alt = alt; dlgCap.textContent = `${alt}. Real RedShadow screen, demo data.`;
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  }
  $('#shot-close').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });

  if (reduce) {
    // static: first sweep already done
    while (col < COLS) step();
  } else {
    for (let k = 0; k < 5; k++) step(); // start with a few findings already on screen
    let running = false;
    const start = () => { if (!running) { running = true; timer = setInterval(step, 700); } };
    const stop = () => { running = false; clearInterval(timer); };
    new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop())).observe(hero);
    document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
    // tilt toward the pointer
    hero.addEventListener('pointermove', (e) => {
      if (innerWidth < 900) return;
      const r = hero.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      win.style.setProperty('--ry', `${-14 + x * 10}deg`); win.style.setProperty('--rx', `${5 - y * 8}deg`);
    });
    hero.addEventListener('pointerleave', () => { win.style.removeProperty('--ry'); win.style.removeProperty('--rx'); });
  }
}
