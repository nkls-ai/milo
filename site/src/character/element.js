// <milo-character>: brings a server-rendered Milo to life. It keeps every pose number on a spring
// (the app's Pip motion: response 0.5 s, damping 0.78) and redraws the SVG only while something moves.
//
//   el.pose = 'listening'        settle into a named pose
//   await el.play('toss')        run a gesture on top of the pose
//   el.lookAt(x, y)              look toward a point on the page (client coordinates), null to stop
//   el.flying = true             flap while he travels
//   el.blinking = false          stop the idle blinks (asleep)
import { rig } from './index.js';

const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const RESPONSE = 0.5, DAMPING = 0.78;
const OMEGA = (2 * Math.PI) / RESPONSE;
const NUMERIC = Object.keys(rig.defaults).filter((k) => typeof rig.defaults[k] === 'number' || rig.defaults[k] === null);

class MiloCharacter extends HTMLElement {
  connectedCallback() {
    if (this._ready) return;
    this._ready = true;
    this.uid = this.dataset.uid || `mc${Math.random().toString(36).slice(2, 7)}`;
    this.svg = this.querySelector('svg');
    this._pose = this.dataset.pose || 'idle';
    this._gaze = null;
    this._gesture = null; // { frames, i, until, resolve }
    this._flying = false;
    this._blinking = this.dataset.blink !== 'off';
    this._blink = 0;
    // pose numbers the server drew with (small, extras...), kept under everything else
    this._base = this.dataset.extra ? JSON.parse(this.dataset.extra) : {};
    this._extra = {};
    this.cur = this._target();
    this.vel = Object.fromEntries(NUMERIC.map((k) => [k, 0]));
    this._last = 0;
    this._raf = 0;
    this._lastDrawn = '';
    this._scheduleBlink();
    this._io = new IntersectionObserver(([e]) => {
      this._visible = e.isIntersecting;
      if (this._visible) this._kick();
    });
    this._visible = true;
    this._io.observe(this);
  }

  disconnectedCallback() {
    this._io?.disconnect();
    cancelAnimationFrame(this._raf);
    clearTimeout(this._blinkTimer);
  }

  get pose() {
    return this._pose;
  }
  set pose(name) {
    if (name === this._pose) return;
    this._pose = name;
    this.dataset.pose = name;
    const label = this.getAttribute('aria-label') !== null;
    if (label && this.dataset.describe !== 'off') this.setAttribute('aria-label', rig.describe(name));
    this._kick();
  }

  /** Extra pose numbers on top of the named pose, e.g. { turn: 0.3 }. */
  set extra(p) {
    this._extra = p || {};
    this._kick();
  }

  set flying(on) {
    if (on === this._flying) return;
    this._flying = on;
    this._kick();
  }
  get flying() {
    return this._flying;
  }

  set blinking(on) {
    this._blinking = on;
    if (on) this._scheduleBlink();
  }

  /** Look toward a point in client coordinates, or stop looking (null). */
  lookAt(x, y) {
    if (x == null) {
      this._gaze = null;
    } else {
      const r = this.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height * 0.48;
      const dx = x - cx, dy = y - cy;
      const d = Math.hypot(dx, dy) || 1;
      const reach = Math.min(1, d / (r.width * 1.6));
      this._gaze = [(dx / d) * reach, (dy / d) * reach * 0.8];
    }
    this._kick();
  }

  /** Run a gesture; resolves when it has finished. */
  play(name) {
    const frames = rig.gestures[name];
    if (!frames || reduce.matches) return Promise.resolve();
    if (this._gesture) this._gesture.resolve();
    return new Promise((resolve) => {
      this._gesture = { frames, i: 0, until: performance.now() + frames[0].ms, resolve };
      this._kick();
    });
  }

  _scheduleBlink() {
    clearTimeout(this._blinkTimer);
    if (!this._blinking || reduce.matches) return;
    this._blinkTimer = setTimeout(() => {
      if (this._visible && this._pose !== 'sleepy' && document.visibilityState === 'visible') {
        this._blink = performance.now() + 130;
        // now and then a double blink
        if (Math.random() < 0.18) setTimeout(() => { this._blink = performance.now() + 120; this._kick(); }, 260);
        this._kick();
      }
      this._scheduleBlink();
    }, 2200 + Math.random() * 4200);
  }

  _target(now = performance.now()) {
    let p = { ...rig.poses[this._pose], ...this._base, ...this._extra };
    // poses that already say where he looks (thinking, working...) keep their own gaze
    const gazeOk = this._pose !== 'sleepy' && !('gx' in (rig.poses[this._pose] || {}));
    if (this._gaze && gazeOk) p = { ...p, ...rig.gaze(this._gaze[0], this._gaze[1]) };
    if (this._gesture) p = { ...p, ...this._gesture.frames[this._gesture.i].p };
    if (this._flying) p = { ...p, ...rig.flap(now / 1000), lean: -6 };
    const full = rig.resolve(p);
    if (this._blink > now) Object.assign(full, { lidL: 1, lidR: 1 });
    return full;
  }

  _kick() {
    if (!this._raf) this._raf = requestAnimationFrame((t) => this._tick(t));
  }

  _tick(now) {
    this._raf = 0;
    if (this._gesture && now >= this._gesture.until) {
      const g = this._gesture;
      g.i++;
      if (g.i >= g.frames.length) {
        this._gesture = null;
        g.resolve();
      } else g.until = now + g.frames[g.i].ms;
    }
    const target = this._target(now);
    const dt = Math.min(0.05, this._last ? (now - this._last) / 1000 : 1 / 60);
    this._last = now;
    let moving = false;
    const snap = reduce.matches;
    const next = { ...target };
    for (const k of NUMERIC) {
      const goal = target[k] ?? 0;
      let x = this.cur[k] ?? goal;
      if (snap || ((k === 'lidL' || k === 'lidR') && this._blink > now)) {
        // blinks close at once, and with reduced motion everything jumps straight there
        next[k] = goal;
        this.vel[k] = 0;
        if (Math.abs(goal - x) > 1e-3) moving = true;
        continue;
      }
      let v = this.vel[k];
      const a = OMEGA * OMEGA * (goal - x) - 2 * DAMPING * OMEGA * v;
      v += a * dt;
      x += v * dt;
      if (Math.abs(goal - x) < 1e-3 && Math.abs(v) < 1e-3) { x = goal; v = 0; } else moving = true;
      next[k] = x;
      this.vel[k] = v;
    }
    this.cur = next;
    this._draw(next, moving || this._blink > now || !!this._gesture);
    const busy = moving || this._gesture || this._flying || this._blink > now;
    if (busy && this._visible) this._kick();
    else this._last = 0;
  }

  _draw(p, moving) {
    const { defs, body } = rig.draw(p, this.uid);
    const html = defs + body;
    // The first time through, the server's drawing is already right unless something moves.
    if (!this._lastDrawn && !moving) { this._lastDrawn = html; return; }
    if (html === this._lastDrawn) return;
    this._lastDrawn = html;
    this.svg.innerHTML = html;
  }
}

if (!customElements.get('milo-character')) customElements.define('milo-character', MiloCharacter);
