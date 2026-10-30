// <milo-character>: brings a server-rendered Milo to life with the app's motion (WrenMotion.swift).
// Every pose number has its own spring, moves are curves of offsets laid on top, the loose parts
// (scarf, tail, head, tuft) are thrown about by the body's motion, and the SVG is redrawn only while
// something moves.
//
//   el.pose = 'listening'        settle into a named pose (and play the moves the change calls for)
//   await el.play('hop')         run a move on top of the pose
//   el.lookAt(x, y)              look toward a point on the page (client coordinates), null to stop
//   el.flying = true             take off and flap while he travels; false lands
//   el.blinking = false          stop the idle blinks (asleep)
//   el.life = true               idle habits now and then: glances, bobs, a tail flick, a scarf tug
import { rig } from './index.js';

const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const CH = rig.channels;
const STIFF = CH.map((k) => (2 * Math.PI / rig.springs[k][0]) ** 2);
const DAMP = CH.map((k) => (4 * Math.PI * rig.springs[k][1]) / rig.springs[k][0]);
const EPS = CH.map((k) => rig.epsilon(k));
const STEP = 1 / 240;
/** Blink: shut in 70 ms, held 40 ms, open again in 120 ms. */
const BLINK = { close: 0.07, hold: 0.04, open: 0.12 };
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/** A clip track's offset at `t`: a Catmull-Rom curve through its keys, at rest on the first and last. */
function sample(keys, t) {
  const first = keys[0], last = keys[keys.length - 1];
  if (t <= first[0]) return first[1];
  if (t >= last[0]) return last[1];
  let i = keys.findIndex((k) => k[0] > t) - 1;
  const a = keys[i], b = keys[i + 1];
  const span = b[0] - a[0];
  if (span <= 0) return b[1];
  const u = (t - a[0]) / span;
  const slope = (j) => (j > 0 && j < keys.length - 1 ? ((keys[j + 1][1] - keys[j - 1][1]) / (keys[j + 1][0] - keys[j - 1][0])) * span : 0);
  const m0 = slope(i), m1 = slope(i + 1);
  const u2 = u * u, u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * a[1] + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * b[1] + (u3 - u2) * m1;
}

class MiloCharacter extends HTMLElement {
  connectedCallback() {
    if (this._ready) return;
    this._ready = true;
    this.uid = this.dataset.uid || `mc${Math.random().toString(36).slice(2, 7)}`;
    this.svg = this.querySelector('svg');
    this._pose = this.dataset.pose || 'idle';
    this._gaze = null;
    this._glance = null;
    this._flying = false;
    this._blinking = this.dataset.blink !== 'off';
    // pose numbers the server drew with (small, extras...), kept under everything else
    this._base = this.dataset.extra ? JSON.parse(this.dataset.extra) : {};
    this._extra = {};
    this.time = 0;
    this.clips = []; // { clip, start, resolve }
    this._blinkAt = null;
    this._phase = 0;
    this._prev = null; // knot, rise and lean last substep, for the forces on the loose parts
    this._speed = [0, 0, 0];
    const aim = this._target();
    this.val = CH.map((k) => aim[k]);
    this.vel = CH.map(() => 0);
    this._last = 0;
    this._raf = 0;
    // what the server drew, so the first frame only redraws if something already changed
    this._aim = aim;
    this._lastDrawn = this._html();
    this._scheduleBlink();
    this._visible = true;
    this._io = new IntersectionObserver(([e]) => {
      this._visible = e.isIntersecting;
      if (this._visible) this._kick();
    });
    this._io.observe(this);
  }

  disconnectedCallback() {
    this._io?.disconnect();
    cancelAnimationFrame(this._raf);
    clearTimeout(this._blinkTimer);
    clearTimeout(this._lifeTimer);
  }

  get pose() {
    return this._pose;
  }
  set pose(name) {
    if (name === this._pose) return;
    const from = this._pose;
    this._pose = name;
    this.dataset.pose = name;
    const label = this.getAttribute('aria-label') !== null;
    if (label && this.dataset.describe !== 'off') this.setAttribute('aria-label', rig.describe(name));
    for (const c of rig.cues(from, name)) this.play(c);
    this._kick();
  }

  /** Extra pose numbers on top of the named pose, e.g. { beak: 0.4 }. */
  set extra(p) {
    this._extra = p || {};
    this._kick();
  }

  set flying(on) {
    if (on === this._flying) return;
    this._flying = on;
    if (on) { this.play('takeoff'); this.play('holdOff'); } else this.play('land');
    this._kick();
  }
  get flying() {
    return this._flying;
  }

  set blinking(on) {
    this._blinking = on;
    if (on) this._scheduleBlink();
  }

  set life(on) {
    this._life = on;
    this._scheduleLife();
  }

  /** Look toward a point in client coordinates, or stop looking (null). */
  lookAt(x, y) {
    if (x == null) {
      this._gaze = null;
    } else {
      const r = this.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height * 0.52;
      const dx = x - cx, dy = y - cy;
      const d = Math.hypot(dx, dy) || 1;
      const reach = Math.min(1, d / (r.width * 1.6));
      this._gaze = [(dx / d) * reach, (dy / d) * reach * 0.8];
    }
    this._kick();
  }

  /** Run a move; resolves when it has finished. Off screen or with reduced motion there is nothing to see. */
  play(name) {
    const clip = rig.gestures[name];
    if (!clip || reduce.matches || !this._visible || !this.isConnected) return Promise.resolve();
    for (const c of this.clips) if (c.clip === clip) c.resolve();
    this.clips = this.clips.filter((c) => c.clip !== clip);
    return new Promise((resolve) => {
      this.clips.push({ clip, start: this.time, resolve });
      this._kick();
    });
  }

  _scheduleBlink() {
    clearTimeout(this._blinkTimer);
    if (!this._blinking || reduce.matches) return;
    this._blinkTimer = setTimeout(() => {
      if (this._visible && this._pose !== 'sleepy' && document.visibilityState === 'visible') {
        this._blink();
        // now and then a double blink
        if (Math.random() < 0.18) setTimeout(() => this._blink(), 300);
      }
      this._scheduleBlink();
    }, 2500 + Math.random() * 3500);
  }

  _blink() {
    if (this._blinkAt != null && this.time - this._blinkAt < BLINK.close + BLINK.hold) return;
    this._blinkAt = this.time;
    this._kick();
  }

  _scheduleLife() {
    clearTimeout(this._lifeTimer);
    if (!this._life || reduce.matches) return;
    this._lifeTimer = setTimeout(() => {
      if (this._visible && this._pose === 'idle' && !this._gaze && !this._flying && !this.clips.length && document.visibilityState === 'visible') {
        const roll = Math.random();
        const habit = rig.habits.find(([p]) => roll < p);
        if (habit) this.play(habit[1]);
        else {
          const a = Math.random() * 2 * Math.PI, reach = 0.5 + Math.random() * 0.5;
          this._glance = [Math.cos(a) * reach, Math.sin(a) * reach * 0.6];
          this._kick();
          setTimeout(() => { this._glance = null; this._kick(); }, 1200);
        }
      }
      this._scheduleLife();
    }, 5000 + Math.random() * 7000);
  }

  /** Where the springs head: the pose, what the page laid over it, his gaze and flight. */
  _target() {
    const own = rig.poses[this._pose] || {};
    let p = { ...own, ...this._base };
    // poses that already say where he looks (thinking, working...) keep their own gaze
    const gazeOk = this._pose !== 'sleepy' && !('gazeX' in own);
    if (gazeOk && this._gaze) p = { ...p, ...rig.gaze(this._gaze[0], this._gaze[1]) };
    else if (gazeOk && this._glance) p = { ...p, gazeX: this._glance[0], gazeY: this._glance[1], headTilt: (p.headTilt ?? rig.defaults.headTilt) + 5 };
    if (this._flying) p = { ...p, ...rig.flying };
    p = { ...p, ...this._extra };
    const full = rig.resolve(p);
    for (const { clip, start } of this.clips) {
      if (clip.mode !== 'target') continue;
      for (const k in clip.tracks) full[k] += sample(clip.tracks[k], this.time - start);
    }
    return full;
  }

  /** The spring values with the moves laid on top; with `raw`, without blink, wingbeat or limits. */
  _output(raw = false) {
    const p = {};
    CH.forEach((k, i) => { p[k] = this.val[i]; });
    for (const { clip, start } of this.clips) {
      if (clip.mode !== 'add') continue;
      for (const k in clip.tracks) p[k] += sample(clip.tracks[k], this.time - start);
    }
    if (raw) return p;
    if (this._blinkAt != null) {
      const t = this.time - this._blinkAt, b = BLINK;
      const shut = t < b.close ? smooth(0, 1, t / b.close) : t < b.close + b.hold ? 1 : 1 - smooth(0, 1, (t - b.close - b.hold) / b.open);
      p.lidL += (1 - p.lidL) * shut;
      p.lidR += (1 - p.lidR) * shut;
      p.browL -= 0.12 * shut;
      p.browR -= 0.12 * shut;
    }
    if (p.fly > 0.05) {
      // wingbeats: a fast downstroke, a slower recovery; the body bobs against them
      const s = Math.sin(this._phase), w = smooth(0.05, 0.6, p.fly);
      const beat = s > 0 ? s : s * 0.75;
      p.wingL += beat * 34 * w;
      p.wingR += beat * 34 * w;
      p.lift += -Math.cos(this._phase) * 2.2 * w;
      p.squash += Math.sin(this._phase + 0.6) * 0.025 * w;
      p.scarf += Math.sin(this._phase - 1.2) * 7 * w;
    }
    for (const k of ['lidL', 'lidR', 'lowerL', 'lowerR', 'beak', 'blush', 'openL', 'openR', 'fly', 'feet', 'scarfUp']) p[k] = clamp(p[k], 0, 1);
    p.scarfToss = clamp(p.scarfToss, -0.1, 1.1);
    return p;
  }

  get _flapping() {
    return this._aim.fly > 0.5 || this.val[CH.indexOf('fly')] > 0.05;
  }

  /** The scarf end swings when the knot is thrown about, the tail whips against it, the head lags the
   * lean, and the tuft sways behind the head and is pressed flat as he goes up. */
  _throw(h) {
    const now = this._output(true);
    const knot = 100 + 52 * Math.sin(((now.turn * 50 + 32) * Math.PI) / 180) + (60 * now.lean * Math.PI) / 180 + now.headX * 0.3;
    const up = now.lift + now.squash * 40;
    const prev = this._prev;
    this._prev = [knot, up, now.lean];
    if (!prev) { this._speed = [0, 0, 0]; return; }
    const speed = [(knot - prev[0]) / h, (up - prev[1]) / h, (now.lean - prev[2]) / h];
    // clamped: a pop in the target would otherwise fling the scarf round his neck
    const ax = clamp((speed[0] - this._speed[0]) / h, -4000, 4000);
    const ay = clamp((speed[1] - this._speed[1]) / h, -6000, 6000);
    const al = clamp((speed[2] - this._speed[2]) / h, -3000, 3000);
    this._speed = speed;
    const v = this.vel, I = this._idx;
    v[I.scarf] += (ax * 2.6 - ay * 0.18) * h;
    v[I.tail] += (-ay * 0.16 + ax * 0.35 * (now.turn > 0 ? -1 : 1)) * h;
    v[I.headTilt] += -al * 0.5 * h;
    v[I.headY] += ay * 0.012 * h;
    v[I.crestSway] += (-ax * 1.6 - al * 0.9) * h;
    v[I.crest] += -ay * 0.004 * h;
  }

  get _idx() {
    return (MiloCharacter.idx ??= Object.fromEntries(CH.map((k, i) => [k, i])));
  }

  _kick() {
    if (!this._raf && this.svg) this._raf = requestAnimationFrame((t) => this._tick(t));
  }

  _tick(now) {
    this._raf = 0;
    const dt = Math.min(0.1, this._last ? (now - this._last) / 1000 : 1 / 60);
    this._last = now;
    if (reduce.matches) {
      // no motion: straight to the pose
      this.clips.forEach((c) => c.resolve());
      this.clips = [];
      this._blinkAt = null;
      const aim = this._target();
      this.val = CH.map((k) => aim[k]);
      this.vel = CH.map(() => 0);
      this._aim = aim;
      this._draw();
      this._last = 0;
      return;
    }
    let left = dt;
    while (left > 1e-9) {
      const h = Math.min(STEP, left);
      this.time += h;
      this._aim = this._target();
      CH.forEach((k, i) => {
        this.vel[i] += (-STIFF[i] * (this.val[i] - this._aim[k]) - DAMP[i] * this.vel[i]) * h;
      });
      this._throw(h);
      CH.forEach((_, i) => { this.val[i] += this.vel[i] * h; });
      if (this._flapping) this._phase += h * 2 * Math.PI * 4.6;
      left -= h;
    }
    for (const c of this.clips.filter((c) => this.time - c.start > c.clip.duration)) c.resolve();
    this.clips = this.clips.filter((c) => this.time - c.start <= c.clip.duration);
    if (this._blinkAt != null && this.time - this._blinkAt > BLINK.close + BLINK.hold + BLINK.open) this._blinkAt = null;
    const aim = this._target();
    this._aim = aim;
    const settled = !this.clips.length && this._blinkAt == null && !this._flapping
      && CH.every((k, i) => Math.abs(this.val[i] - aim[k]) < EPS[i] && Math.abs(this.vel[i]) < EPS[i] * 8);
    if (settled) {
      this.val = CH.map((k) => aim[k]);
      this.vel = CH.map(() => 0);
      this._prev = null;
    }
    this._draw();
    if (!settled && this._visible) this._kick();
    else this._last = 0;
  }

  _html() {
    const aim = this._aim ?? this._target();
    const { defs, body } = rig.draw({ ...this._output(), small: aim.small, extras: aim.extras }, this.uid);
    return defs + body;
  }

  _draw() {
    const html = this._html();
    if (html === this._lastDrawn) return;
    this._lastDrawn = html;
    this.svg.innerHTML = html;
  }
}

if (!customElements.get('milo-character')) customElements.define('milo-character', MiloCharacter);
