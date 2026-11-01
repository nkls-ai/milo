// A small seeded generator (mulberry32): the same moves for the same seed, so tests can replay a day. The Mac uses
// SplitMix64; JavaScript has no 64-bit integers, and nothing depends on the exact sequence.
export class SeededRandom {
    constructor(seed) { this.state = (seed >>> 0) || 1 }

    next() {
        this.state = (this.state + 0x6D2B79F5) >>> 0
        let z = this.state
        z = Math.imul(z ^ (z >>> 15), z | 1)
        z ^= z + Math.imul(z ^ (z >>> 7), z | 61)
        return ((z ^ (z >>> 14)) >>> 0) / 4294967296
    }

    between(lo, hi) { return lo + (hi - lo) * this.next() }
    chance(p) { return this.next() < p }
}
