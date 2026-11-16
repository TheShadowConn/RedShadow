/* RedShadow site 3D: the hero eclipse (WebGL, no library) and the product screen deck (CSS 3D).
   Both rest under prefers-reduced-motion and keep a still fallback when WebGL is refused. */
(function () {
  'use strict';
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- hero: a cream sphere that casts a red shadow ---------- */
  var VERT = 'attribute vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }';
  var FRAG = [
    'precision highp float;',
    'uniform vec2 uRes; uniform vec3 uCam; uniform vec2 uLight; uniform float uMoon;',
    'uniform vec3 BG;',   /* the page ground, read from the body */
    'const vec3 RED = vec3(0.9373, 0.1373, 0.2353);',  /* #ef233c Racing Red */
    'const vec3 DEEP = vec3(0.47, 0.03, 0.10);',
    'float hit(vec3 ro, vec3 rd, vec4 s){ vec3 oc = ro - s.xyz; float b = dot(oc, rd); float c = dot(oc, oc) - s.w*s.w; float h = b*b - c; if (h < 0.0) return -1.0; return -b - sqrt(h); }',
    'float soft(vec3 ro, vec3 rd, vec4 s, float k){ vec3 oc = ro - s.xyz; float b = dot(oc, rd); float c = dot(oc, oc) - s.w*s.w; float h = b*b - c;',
    '  float d = -s.w + sqrt(max(0.0, s.w*s.w - h)); float t = -b - sqrt(max(0.0, h)); return t < 0.0 ? 1.0 : smoothstep(0.0, 1.0, k*d/t); }',
    'vec3 shade(vec3 ro, vec3 rd, vec3 L, vec4 A, vec4 B){',
    '  float tA = hit(ro, rd, A), tB = hit(ro, rd, B);',
    '  float tF = rd.y < -0.0001 ? -ro.y/rd.y : -1.0;',
    '  float t = 1e9; int id = 0;',
    '  if (tF > 0.0) { t = tF; id = 1; }',
    '  if (tA > 0.0 && tA < t) { t = tA; id = 2; }',
    '  if (tB > 0.0 && tB < t) { t = tB; id = 3; }',
    '  if (id == 0) return BG;',
    '  vec3 p = ro + rd*t;',
    '  if (id == 1) {',
    '    float sh = min(soft(p, L, A, 5.0), soft(p, L, B, 5.0));',
    '    float near = exp(-1.6*max(length(p.xz) - 0.25, 0.0));',
    '    vec3 c = mix(BG, mix(RED, DEEP, 0.45*near), (1.0 - sh)*0.94);',
    '    c *= 1.0 - 0.07*exp(-2.2*length(p.xz))*sh;',
    '    return mix(c, BG, smoothstep(5.0, 13.0, length(p.xz)));',
    '  }',
    '  if (id == 2) {',
    '    vec3 n = normalize(p - A.xyz); float d = dot(n, L);',
    '    float lit = smoothstep(-0.06, 0.30, d) * soft(p + n*0.004, L, B, 9.0);',
    '    vec3 litC = mix(vec3(0.925, 0.895, 0.855), vec3(1.0, 0.995, 0.985), smoothstep(0.0, 1.0, d));',
    '    vec3 shC = mix(RED, DEEP, 0.75*smoothstep(0.1, -0.9, d)) + 0.07*max(-n.y, 0.0);',
    '    vec3 c = mix(shC, litC, lit);',
    '    float fr = pow(1.0 - max(dot(n, -rd), 0.0), 3.0);',
    '    c *= 1.0 - 0.16*fr;',
    '    c += 0.22*lit*pow(max(dot(reflect(-L, n), -rd), 0.0), 36.0);',
    '    return c;',
    '  }',
    '  vec3 n = normalize(p - B.xyz); float d = dot(n, L);',
    '  float lit = smoothstep(-0.05, 0.45, d) * soft(p + n*0.004, L, A, 9.0);',
    '  vec3 c = mix(DEEP, RED, lit);',
    '  c += 0.10*pow(1.0 - max(dot(n, -rd), 0.0), 3.0);',
    '  c += 0.55*lit*pow(max(dot(reflect(-L, n), -rd), 0.0), 60.0);',
    '  return c;',
    '}',
    'void main(){',
    '  float asp = uRes.x/uRes.y;',
    '  vec3 ta = vec3(0.35, 0.72, 0.0);',
    '  float dist = uCam.z * max(1.0, 1.25/asp);',
    '  vec3 ro = ta + dist*vec3(cos(uCam.y)*sin(uCam.x), sin(uCam.y), cos(uCam.y)*cos(uCam.x));',
    '  vec3 f = normalize(ta - ro), r = normalize(cross(f, vec3(0.0, 1.0, 0.0))), u = cross(r, f);',
    '  float az = uCam.x + uLight.x;',
    '  vec3 L = normalize(vec3(cos(uLight.y)*sin(az), sin(uLight.y), cos(uLight.y)*cos(az)));',
    '  vec4 A = vec4(0.0, 1.0, 0.0, 1.0);',
    '  vec4 B = vec4(1.78*cos(uMoon), 1.05 + 0.5*sin(uMoon), 1.78*sin(uMoon), 0.3);',
    '  vec3 col = vec3(0.0);',
    '  for (int i = 0; i < 4; i++) {',
    '    vec2 o = vec2(mod(float(i), 2.0), floor(float(i)/2.0))*0.5 - 0.25;',
    '    vec2 uv = (2.0*(gl_FragCoord.xy + o) - uRes)/uRes.y;',
    '    col += shade(ro, normalize(uv.x*r + uv.y*u + 4.3*f), L, A, B);',
    '  }',
    '  gl_FragColor = vec4(col*0.25, 1.0);',
    '}'
  ].join('\n');

  function eclipse(root) {
    var canvas = root.querySelector('canvas'), pause = root.querySelector('.ecl__pause');
    var gl = null;
    try { gl = canvas.getContext('webgl', { alpha: false, antialias: false, powerPreference: 'low-power' }); } catch (e) { gl = null; }
    if (!gl) { root.classList.add('is-still'); return; }

    function compile(type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; }
    var vs = compile(gl.VERTEX_SHADER, VERT), fs = compile(gl.FRAGMENT_SHADER, FRAG);
    var prog = gl.createProgram();
    if (!vs || !fs) { root.classList.add('is-still'); return; }
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { root.classList.add('is-still'); return; }
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var U = { res: gl.getUniformLocation(prog, 'uRes'), cam: gl.getUniformLocation(prog, 'uCam'), light: gl.getUniformLocation(prog, 'uLight'), moon: gl.getUniformLocation(prog, 'uMoon'), bg: gl.getUniformLocation(prog, 'BG') };
    var m = (getComputedStyle(document.body).backgroundColor.match(/[\d.]+/g) || [247, 244, 239]).map(Number);
    gl.uniform3f(U.bg, m[0] / 255, m[1] / 255, m[2] / 255);

    var s = { yaw: 0.5, pitch: 0.3, lx: -1.0, le: 0.62, moon: 2.4 };      /* drawn state */
    var t = { yaw: 0.5, pitch: 0.3, lx: -1.0, le: 0.62 };                 /* target state */
    var paused = reduced, visible = true, dirty = true, drag = null, last = 0, raf = 0;

    function size() {
      var dpr = Math.min(window.devicePixelRatio || 1, 1.5), w = Math.max(1, Math.round(root.clientWidth * dpr)), h = Math.max(1, Math.round(root.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h); dirty = true; }
    }
    function frame(now) {
      raf = 0;
      var dt = Math.min((now - last) / 1000 || 0, 0.05); last = now;
      var k = reduced ? 1 : 1 - Math.pow(0.001, dt), moving = false;
      ['yaw', 'pitch', 'lx', 'le'].forEach(function (key) {
        var d = t[key] - s[key];
        if (Math.abs(d) > 0.0005) { s[key] += d * k; moving = true; } else { s[key] = t[key]; }
      });
      if (!paused) { s.moon += dt * 0.38; moving = true; }
      if (moving || dirty) {
        dirty = false;
        gl.uniform2f(U.res, canvas.width, canvas.height);
        gl.uniform3f(U.cam, s.yaw, s.pitch, 6.0);
        gl.uniform2f(U.light, s.lx, s.le);
        gl.uniform1f(U.moon, s.moon);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        root.classList.add('is-live');
      }
      if (visible && (moving || !paused)) schedule();
    }
    function schedule() { if (!raf && visible) raf = requestAnimationFrame(frame); }
    function wake() { last = performance.now(); schedule(); }

    canvas.addEventListener('pointerdown', function (e) {
      drag = { x: e.clientX, y: e.clientY, yaw: t.yaw, pitch: t.pitch, touch: e.pointerType === 'touch' };
      try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
      root.classList.add('is-drag');
    });
    canvas.addEventListener('pointermove', function (e) {
      if (drag) {
        t.yaw = drag.yaw - (e.clientX - drag.x) * 0.006;
        if (!drag.touch) t.pitch = Math.min(0.8, Math.max(0.1, drag.pitch + (e.clientY - drag.y) * 0.004));
      } else if (e.pointerType !== 'touch') {
        var b = canvas.getBoundingClientRect();
        t.lx = ((e.clientX - b.left) / b.width - 0.5) * 2.8;
        t.le = 0.36 + (1 - (e.clientY - b.top) / b.height) * 0.72;
      }
      wake();
    });
    function end() { drag = null; root.classList.remove('is-drag'); }
    canvas.addEventListener('pointerup', end);
    canvas.addEventListener('pointercancel', end);
    canvas.addEventListener('keydown', function (e) {
      var step = 0.18;
      if (e.key === 'ArrowLeft') t.yaw += step; else if (e.key === 'ArrowRight') t.yaw -= step;
      else if (e.key === 'ArrowUp') t.pitch = Math.min(0.8, t.pitch + 0.08); else if (e.key === 'ArrowDown') t.pitch = Math.max(0.1, t.pitch - 0.08);
      else return;
      e.preventDefault(); wake();
    });
    function setPaused(v) {
      paused = v;
      pause.setAttribute('aria-pressed', String(v));
      pause.setAttribute('aria-label', v ? 'Play the orbit' : 'Pause the orbit');
      wake();
    }
    pause.addEventListener('click', function () { setPaused(!paused); });
    setPaused(paused);

    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (visible) wake(); }).observe(root);
    }
    document.addEventListener('visibilitychange', function () { if (!document.hidden) wake(); });
    if ('ResizeObserver' in window) new ResizeObserver(function () { size(); wake(); }).observe(root);
    else window.addEventListener('resize', function () { size(); wake(); });
    canvas.addEventListener('webglcontextlost', function (e) { e.preventDefault(); root.classList.remove('is-live'); root.classList.add('is-still'); });
    size(); wake();
  }

  /* ---------- product: the four screens as a deck in depth ---------- */
  function deck(root) {
    var panes = [].slice.call(root.querySelectorAll('.deck__pane'));
    var buttons = [].slice.call(document.querySelectorAll('[data-pane]'));
    var tilt = root.querySelector('.deck__tilt');
    var n = panes.length, base = { rx: 9, ry: -22 }, drag = null, moved = false;

    function select(i) {
      panes.forEach(function (p, idx) {
        var k = (idx - i + n) % n;
        p.style.setProperty('--k', k);
        p.classList.toggle('is-front', k === 0);
        p.setAttribute('aria-hidden', k === 0 ? 'false' : 'true');
      });
      buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(+b.dataset.pane === i)); });
    }
    function pose(rx, ry) { tilt.style.setProperty('--rx', rx + 'deg'); tilt.style.setProperty('--ry', ry + 'deg'); }

    buttons.forEach(function (b) { b.addEventListener('click', function () { select(+b.dataset.pane); }); });
    panes.forEach(function (p, idx) {
      p.addEventListener('click', function () { if (!moved) select(idx); });
      p.addEventListener('dragstart', function (e) { e.preventDefault(); });
    });
    root.addEventListener('pointerdown', function (e) {
      drag = { x: e.clientX, y: e.clientY, ry: parseFloat(tilt.style.getPropertyValue('--ry')) || base.ry, rx: parseFloat(tilt.style.getPropertyValue('--rx')) || base.rx, touch: e.pointerType === 'touch' };
      moved = false;
    });
    window.addEventListener('pointermove', function (e) {
      if (drag) {
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 5) { moved = true; root.classList.add('is-drag'); }
        if (moved) pose(drag.touch ? drag.rx : Math.min(26, Math.max(-6, drag.rx - dy * 0.15)), Math.min(24, Math.max(-52, drag.ry + dx * 0.25)));
      }
    });
    function end() { if (!drag) return; drag = null; root.classList.remove('is-drag'); }
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
    root.addEventListener('pointermove', function (e) {
      if (drag || reduced || e.pointerType === 'touch') return;
      var b = root.getBoundingClientRect();
      pose(base.rx - ((e.clientY - b.top) / b.height - 0.5) * 8, base.ry + ((e.clientX - b.left) / b.width - 0.5) * 12);
    });
    root.addEventListener('pointerleave', function () { if (!drag) pose(base.rx, base.ry); });
    select(0);
  }

  var e = document.getElementById('ecl'), d = document.getElementById('deck');
  if (e) eclipse(e);
  if (d) deck(d);
})();
