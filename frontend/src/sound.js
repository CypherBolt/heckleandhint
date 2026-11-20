// Sound board, synthesised live with the Web Audio API (no audio files).
// Only the big screen plays sounds. Browsers block audio until a tap, so the
// screen shows "Tap to start" first and calls unlockAudio() on that tap.

let ctx = null

export function audioReady() {
  return !!ctx && ctx.state === 'running'
}

export async function unlockAudio() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) return false
    if (!ctx) ctx = new AC()
    if (ctx.state !== 'running') await ctx.resume()
    return ctx.state === 'running'
  } catch {
    return false
  }
}

function noiseBuffer(seconds) {
  const len = Math.floor(ctx.sampleRate * seconds)
  const buf = ctx.createBuffer(1, len, ctx.sampleRate)
  const data = buf.getChannelData(0)
  for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1
  return buf
}

function env(gainNode, t, attack, peak, decay) {
  gainNode.gain.setValueAtTime(0.0001, t)
  gainNode.gain.exponentialRampToValueAtTime(peak, t + attack)
  gainNode.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay)
}

function tone(type, freq, t, dur, peak = 0.4, freqEnd = null) {
  const o = ctx.createOscillator()
  const g = ctx.createGain()
  o.type = type
  o.frequency.setValueAtTime(freq, t)
  if (freqEnd) o.frequency.exponentialRampToValueAtTime(freqEnd, t + dur)
  env(g, t, 0.005, peak, dur)
  o.connect(g).connect(ctx.destination)
  o.start(t)
  o.stop(t + dur + 0.05)
}

function noise(t, dur, { peak = 0.4, type = 'highpass', freq = 1000 } = {}) {
  const src = ctx.createBufferSource()
  src.buffer = noiseBuffer(dur + 0.05)
  const f = ctx.createBiquadFilter()
  f.type = type
  f.frequency.value = freq
  const g = ctx.createGain()
  env(g, t, 0.002, peak, dur)
  src.connect(f).connect(g).connect(ctx.destination)
  src.start(t)
}

const SOUNDS = {
  // "ba-dum-tss": two toms and a cymbal
  rimshot(t) {
    tone('sine', 180, t, 0.18, 0.6, 90)
    noise(t, 0.08, { peak: 0.25, type: 'bandpass', freq: 1800 })
    tone('sine', 140, t + 0.17, 0.2, 0.6, 70)
    noise(t + 0.17, 0.08, { peak: 0.25, type: 'bandpass', freq: 1500 })
    noise(t + 0.36, 0.9, { peak: 0.35, type: 'highpass', freq: 6000 })
  },
  // "wah wah wah waaah"
  trombone(t) {
    const notes = [[293.7, 0.45], [277.2, 0.45], [261.6, 0.45], [246.9, 1.4]]
    let at = t
    for (const [f, d] of notes) {
      const o = ctx.createOscillator()
      const lp = ctx.createBiquadFilter()
      const g = ctx.createGain()
      o.type = 'sawtooth'
      o.frequency.setValueAtTime(f, at)
      if (d > 1) { // vibrato on the last note
        const lfo = ctx.createOscillator()
        const lg = ctx.createGain()
        lfo.frequency.value = 6
        lg.gain.value = 6
        lfo.connect(lg).connect(o.frequency)
        lfo.start(at)
        lfo.stop(at + d)
      }
      lp.type = 'lowpass'
      lp.frequency.value = 900
      g.gain.setValueAtTime(0.0001, at)
      g.gain.exponentialRampToValueAtTime(0.3, at + 0.05)
      g.gain.setValueAtTime(0.3, at + d - 0.12)
      g.gain.exponentialRampToValueAtTime(0.0001, at + d)
      o.connect(lp).connect(g).connect(ctx.destination)
      o.start(at)
      o.stop(at + d + 0.05)
      at += d
    }
  },
  airhorn(t) {
    for (const start of [0, 0.32, 0.64]) {
      const d = start === 0.64 ? 0.9 : 0.25
      for (const f of [415, 466, 622]) {
        const o = ctx.createOscillator()
        const g = ctx.createGain()
        o.type = 'sawtooth'
        o.frequency.setValueAtTime(f * 0.97, t + start)
        o.frequency.linearRampToValueAtTime(f, t + start + 0.06)
        g.gain.setValueAtTime(0.0001, t + start)
        g.gain.exponentialRampToValueAtTime(0.12, t + start + 0.02)
        g.gain.setValueAtTime(0.12, t + start + d - 0.05)
        g.gain.exponentialRampToValueAtTime(0.0001, t + start + d)
        o.connect(g).connect(ctx.destination)
        o.start(t + start)
        o.stop(t + start + d + 0.05)
      }
    }
  },
  drumroll(t) {
    const hits = 36
    for (let i = 0; i < hits; i++) {
      const at = t + i * 0.055
      noise(at, 0.05, { peak: 0.08 + (0.25 * i) / hits, type: 'bandpass', freq: 2200 })
    }
    const end = t + hits * 0.055
    tone('sine', 120, end, 0.3, 0.7, 60)
    noise(end, 1.0, { peak: 0.35, type: 'highpass', freq: 5000 })
  },
  ding(t) {
    tone('sine', 1318.5, t, 1.2, 0.35)
    tone('sine', 2637, t, 0.6, 0.12)
  },
  buzz(t) {
    const o = ctx.createOscillator()
    const g = ctx.createGain()
    o.type = 'square'
    o.frequency.value = 98
    g.gain.setValueAtTime(0.0001, t)
    g.gain.exponentialRampToValueAtTime(0.18, t + 0.02)
    g.gain.setValueAtTime(0.18, t + 0.65)
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.75)
    o.connect(g).connect(ctx.destination)
    o.start(t)
    o.stop(t + 0.8)
  },
}

export function playSfx(name) {
  if (!audioReady() || !SOUNDS[name]) return false
  try {
    SOUNDS[name](ctx.currentTime + 0.02)
    return true
  } catch {
    return false
  }
}
