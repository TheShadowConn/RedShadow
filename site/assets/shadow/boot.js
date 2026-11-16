/* Section 2: the install, typed out. Lines match docker-compose.yml (project "redshadow").
   The real commands sit in #cmds for screen readers and the Copy button. */
const $ = (s) => document.querySelector(s);
const box = $('#boot');
if (box) init();

function init() {
  const out = $('#boot-out'), browser = $('#boot-browser'), replay = $('#boot-replay'), copy = $('#copy');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const C = (name, state) => ({ t: 'ok', text: ` ✔ Container redshadow-${name}-1`.padEnd(40) + state });
  const SCRIPT = [
    { t: 'cmd', text: 'git clone https://github.com/TheShadowConn/RedShadow.git' },
    { t: 'dim', text: "Cloning into 'RedShadow'... done." },
    { t: 'cmd', text: 'cd RedShadow' },
    { t: 'cmd', text: 'docker compose up --build -d --wait' },
    C('db', 'Healthy'), C('redis', 'Healthy'), C('migrate', 'Exited'), C('backend', 'Healthy'),
    C('worker', 'Started'), C('reports-worker', 'Started'), C('beat', 'Started'), C('nginx', 'Healthy'),
    { t: 'hi', text: '\nRedShadow is up on https://localhost' },
  ];
  let run = 0;

  const line = (cls, text) => { const s = document.createElement('span'); if (cls) s.className = cls; s.textContent = text; out.appendChild(s); return s; };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  async function play() {
    const me = ++run;
    out.textContent = ''; browser.classList.remove('is-on', 'is-ready');
    const cur = document.createElement('span'); cur.className = 'cur';
    for (const step of SCRIPT) {
      if (me !== run) return;
      if (step.t === 'cmd') {
        line('p', '$ ');
        const s = line('', ''); out.appendChild(cur);
        for (const ch of step.text) { if (me !== run) return; s.textContent += ch; await wait(reduce ? 0 : 22 + Math.random() * 30); }
        cur.remove(); line('', '\n'); await wait(reduce ? 0 : 320);
      } else {
        line(step.t, step.text + '\n'); await wait(reduce ? 0 : step.t === 'ok' ? 180 : 260);
      }
    }
    line('p', '$ '); out.appendChild(cur);
    browser.classList.add('is-on');
    await wait(reduce ? 0 : 1300);
    if (me === run) browser.classList.add('is-ready');
  }

  replay.addEventListener('click', play);
  copy.addEventListener('click', () => {
    const t = $('#cmds').textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(() => { copy.textContent = 'Copied'; }, () => { copy.textContent = 'Select and copy'; });
    setTimeout(() => { copy.textContent = 'Copy'; }, 1800);
  });
  if ('IntersectionObserver' in window && !reduce) {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); play(); } }, { threshold: 0.35 });
    io.observe(box);
  } else play();
}
