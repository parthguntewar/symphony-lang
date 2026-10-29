/**
 * synth.ts
 * High-fidelity, synchronized Web Audio API synthesizer for SymphonyLang Studio.
 * Features dedicated acoustic percussion synthesis for General MIDI drums (Kick, Snare,
 * Hi-Hats, Toms, Claps, Cymbals) with no accidental melodic pitch, and physically-modeled
 * acoustic timbres for Piano, Strings (Violin, Cello), Winds (Flute, Clarinet, Saxophone),
 * Brass (Trumpet), Guitars, Bass, and Drawbar Organ.
 */

export interface NoteTimelineEvent {
  kind: string;
  track?: string;
  channel?: number;
  instrument?: string;
  note?: string;
  midi_number?: number;
  duration?: string;
  beats?: number;
  start_beat?: number;
  start_sec?: number;
  duration_sec?: number;
  bpm?: number;
}

export type PlaybackState = 'stopped' | 'playing' | 'paused';

export class SymphonySynth {
  private ctx: AudioContext | null = null;
  private masterGain: GainNode | null = null;
  private compressor: DynamicsCompressorNode | null = null;
  private noiseBuffer: AudioBuffer | null = null;

  private activeOscillators: OscillatorNode[] = [];
  private activeGains: GainNode[] = [];
  private activeBufferSources: AudioBufferSourceNode[] = [];

  private state: PlaybackState = 'stopped';
  private currentTimeline: NoteTimelineEvent[] = [];
  private currentOffsetSec = 0;
  private playbackStartAudioTime = 0;
  private totalDurationSec = 0;

  private rafId: number | null = null;
  private onProgressCallback?: (progress: number, currentTime: number, totalTime: number) => void;
  private onEndedCallback?: () => void;
  private onStateChangeCallback?: (state: PlaybackState) => void;

  private initAudio() {
    if (!this.ctx) {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new AudioCtx();

      // Master Dynamics Compressor prevents clipping with multiple simultaneous tracks
      this.compressor = this.ctx.createDynamicsCompressor();
      this.compressor.threshold.setValueAtTime(-18, this.ctx.currentTime);
      this.compressor.knee.setValueAtTime(12, this.ctx.currentTime);
      this.compressor.ratio.setValueAtTime(8, this.ctx.currentTime);
      this.compressor.attack.setValueAtTime(0.003, this.ctx.currentTime);
      this.compressor.release.setValueAtTime(0.25, this.ctx.currentTime);

      this.masterGain = this.ctx.createGain();
      this.masterGain.gain.setValueAtTime(0.85, this.ctx.currentTime);

      this.compressor.connect(this.masterGain);
      this.masterGain.connect(this.ctx.destination);

      this.initNoiseBuffer();
    }

    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  /**
   * Creates a reusable 2-second white noise buffer for realistic percussion transients
   * (snare snap, hi-hat shimmer, cymbals, claps, and flute breath).
   */
  private initNoiseBuffer() {
    if (!this.ctx || this.noiseBuffer) return;
    const sampleRate = this.ctx.sampleRate;
    const bufferSize = sampleRate * 2;
    const buffer = this.ctx.createBuffer(1, bufferSize, sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = Math.random() * 2 - 1;
    }
    this.noiseBuffer = buffer;
  }

  public midiToFrequency(midi: number): number {
    return 440 * Math.pow(2, (midi - 69) / 12);
  }

  public setStateChangeCallback(cb: (state: PlaybackState) => void) {
    this.onStateChangeCallback = cb;
  }

  public getState(): PlaybackState {
    return this.state;
  }

  public getTotalDuration(): number {
    return this.totalDurationSec;
  }

  public getCurrentTime(): number {
    if (this.state === 'playing' && this.ctx) {
      const elapsed = (this.ctx.currentTime - this.playbackStartAudioTime) + this.currentOffsetSec;
      return Math.max(0, Math.min(this.totalDurationSec, elapsed));
    }
    return this.currentOffsetSec;
  }

  // =========================================================================
  // DEDICATED GENERAL MIDI PERCUSSION SYNTHESIS (Channel 9 / Drum Kit)
  // Non-pitched acoustic modeling: sub-kick drops, noise snares, metallic cymbals
  // =========================================================================

  private scheduleDrum(
    midiNum: number,
    noteName: string,
    startTime: number,
    _duration: number
  ) {
    if (!this.ctx || !this.compressor || !this.noiseBuffer) return;
    const now = this.ctx.currentTime;
    if (startTime + 0.4 <= now) return;
    const safeStart = Math.max(now + 0.005, startTime);

    const n = (noteName || '').toLowerCase();

    // 1. Kick Drum (Bass Drum 1 / Acoustic Bass Drum - MIDI 35, 36)
    if (midiNum === 35 || midiNum === 36 || n.includes('kick') || n.includes('bass drum') || n === 'c2' || n === 'b1') {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      // Deep sub-pitch envelope: punchy 155Hz drops exponentially to 42Hz
      osc.type = 'sine';
      osc.frequency.setValueAtTime(155, safeStart);
      osc.frequency.exponentialRampToValueAtTime(42, safeStart + 0.08);

      // Volume envelope: instant attack and tight punchy decay
      gain.gain.setValueAtTime(0.85, safeStart);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.32);

      osc.connect(gain);
      gain.connect(this.compressor);

      // Transient attack click
      const clickOsc = this.ctx.createOscillator();
      const clickGain = this.ctx.createGain();
      clickOsc.type = 'triangle';
      clickOsc.frequency.setValueAtTime(320, safeStart);
      clickOsc.frequency.exponentialRampToValueAtTime(60, safeStart + 0.015);
      clickGain.gain.setValueAtTime(0.4, safeStart);
      clickGain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.015);

      clickOsc.connect(clickGain);
      clickGain.connect(this.compressor);

      osc.start(safeStart);
      osc.stop(safeStart + 0.35);
      clickOsc.start(safeStart);
      clickOsc.stop(safeStart + 0.02);

      this.activeOscillators.push(osc, clickOsc);
      this.activeGains.push(gain, clickGain);
      return;
    }

    // 2. Snare Drum (Acoustic Snare - MIDI 38, Electric Snare - MIDI 40)
    if (midiNum === 38 || midiNum === 40 || n.includes('snare') || n === 'd2' || n === 'e2') {
      // Snare Drum Body
      const osc = this.ctx.createOscillator();
      const oscGain = this.ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(185, safeStart);
      osc.frequency.exponentialRampToValueAtTime(130, safeStart + 0.09);
      oscGain.gain.setValueAtTime(0.5, safeStart);
      oscGain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.12);

      osc.connect(oscGain);
      oscGain.connect(this.compressor);

      // Snare Wires / Sizzle (Bandpassed White Noise)
      const noise = this.ctx.createBufferSource();
      noise.buffer = this.noiseBuffer;
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.setValueAtTime(2400, safeStart);
      filter.Q.setValueAtTime(2.0, safeStart);

      const noiseGain = this.ctx.createGain();
      noiseGain.gain.setValueAtTime(0.65, safeStart);
      noiseGain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.19);

      noise.connect(filter);
      filter.connect(noiseGain);
      noiseGain.connect(this.compressor);

      osc.start(safeStart);
      osc.stop(safeStart + 0.14);
      noise.start(safeStart);
      noise.stop(safeStart + 0.22);

      this.activeOscillators.push(osc);
      this.activeBufferSources.push(noise);
      this.activeGains.push(oscGain, noiseGain);
      return;
    }

    // 3. Hand Clap (MIDI 39)
    if (midiNum === 39 || n.includes('clap') || n === 'd#2') {
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.setValueAtTime(1300, safeStart);
      filter.Q.setValueAtTime(1.8, safeStart);

      // Multi-burst transient
      const clapGain = this.ctx.createGain();
      clapGain.gain.setValueAtTime(0.0001, safeStart);
      // Burst 1
      clapGain.gain.setValueAtTime(0.6, safeStart);
      clapGain.gain.exponentialRampToValueAtTime(0.05, safeStart + 0.009);
      // Burst 2
      clapGain.gain.setValueAtTime(0.65, safeStart + 0.011);
      clapGain.gain.exponentialRampToValueAtTime(0.05, safeStart + 0.020);
      // Burst 3 + decay
      clapGain.gain.setValueAtTime(0.7, safeStart + 0.022);
      clapGain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.24);

      const noise = this.ctx.createBufferSource();
      noise.buffer = this.noiseBuffer;

      noise.connect(filter);
      filter.connect(clapGain);
      clapGain.connect(this.compressor);

      noise.start(safeStart);
      noise.stop(safeStart + 0.26);

      this.activeBufferSources.push(noise);
      this.activeGains.push(clapGain);
      return;
    }

    // 4. Closed Hi-Hat (MIDI 42) & Pedal Hi-Hat (MIDI 44)
    if (midiNum === 42 || midiNum === 44 || n.includes('closed') || n.includes('pedal') || n === 'f#2' || n === 'g#2') {
      const isPedal = midiNum === 44 || n.includes('pedal') || n === 'g#2';
      const decay = isPedal ? 0.08 : 0.045;

      const noise = this.ctx.createBufferSource();
      noise.buffer = this.noiseBuffer;

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.setValueAtTime(7400, safeStart);
      filter.Q.setValueAtTime(2.5, safeStart);

      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.55, safeStart);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + decay);

      noise.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      noise.start(safeStart);
      noise.stop(safeStart + decay + 0.02);

      this.activeBufferSources.push(noise);
      this.activeGains.push(gain);
      return;
    }

    // 5. Open Hi-Hat (MIDI 46)
    if (midiNum === 46 || n.includes('open') || n === 'a#2') {
      const decay = 0.35;
      const noise = this.ctx.createBufferSource();
      noise.buffer = this.noiseBuffer;

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.setValueAtTime(6500, safeStart);
      filter.Q.setValueAtTime(2.0, safeStart);

      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.5, safeStart);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + decay);

      noise.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      noise.start(safeStart);
      noise.stop(safeStart + decay + 0.02);

      this.activeBufferSources.push(noise);
      this.activeGains.push(gain);
      return;
    }

    // 6. Crash Cymbal (MIDI 49, 57)
    if (midiNum === 49 || midiNum === 57 || n.includes('crash') || n === 'c#3' || n === 'a3') {
      const decay = 1.6;
      const noise = this.ctx.createBufferSource();
      noise.buffer = this.noiseBuffer;

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.setValueAtTime(5200, safeStart);
      filter.Q.setValueAtTime(1.5, safeStart);

      const gain = this.ctx.createGain();
      gain.gain.setValueAtTime(0.65, safeStart);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + decay);

      noise.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      noise.start(safeStart);
      noise.stop(safeStart + decay + 0.05);

      this.activeBufferSources.push(noise);
      this.activeGains.push(gain);
      return;
    }

    // 7. Ride Cymbal (MIDI 51, 59)
    if (midiNum === 51 || midiNum === 59 || n.includes('ride') || n === 'd#3' || n === 'b3') {
      const decay = 0.85;

      // Resonant Bell Ring
      const bell = this.ctx.createOscillator();
      const bellGain = this.ctx.createGain();
      bell.type = 'sine';
      bell.frequency.setValueAtTime(3600, safeStart);
      bellGain.gain.setValueAtTime(0.18, safeStart);
      bellGain.gain.exponentialRampToValueAtTime(0.0001, safeStart + decay * 0.7);

      bell.connect(bellGain);
      bellGain.connect(this.compressor);

      // Shimmer
      const noise = this.ctx.createBufferSource();
      noise.buffer = this.noiseBuffer;
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.setValueAtTime(6000, safeStart);
      const noiseGain = this.ctx.createGain();
      noiseGain.gain.setValueAtTime(0.25, safeStart);
      noiseGain.gain.exponentialRampToValueAtTime(0.0001, safeStart + decay);

      noise.connect(filter);
      filter.connect(noiseGain);
      noiseGain.connect(this.compressor);

      bell.start(safeStart);
      bell.stop(safeStart + decay);
      noise.start(safeStart);
      noise.stop(safeStart + decay + 0.02);

      this.activeOscillators.push(bell);
      this.activeBufferSources.push(noise);
      this.activeGains.push(bellGain, noiseGain);
      return;
    }

    // 8. Toms (Floor, Low, Mid, High - MIDI 41, 43, 45, 47, 48, 50)
    let startPitch = 190;
    let endPitch = 90;
    if (midiNum === 41 || midiNum === 43 || midiNum === 45 || n.includes('low') || n.includes('floor')) {
      startPitch = 135;
      endPitch = 60;
    } else if (midiNum === 50 || n.includes('high')) {
      startPitch = 250;
      endPitch = 130;
    }

    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(startPitch, safeStart);
    osc.frequency.exponentialRampToValueAtTime(endPitch, safeStart + 0.18);

    gain.gain.setValueAtTime(0.7, safeStart);
    gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + 0.28);

    osc.connect(gain);
    gain.connect(this.compressor);

    osc.start(safeStart);
    osc.stop(safeStart + 0.30);
    this.activeOscillators.push(osc);
    this.activeGains.push(gain);
  }

  // =========================================================================
  // HIGH-FIDELITY MELODIC INSTRUMENT SYNTHESIS
  // Distinct physical acoustic envelopes: Bowed Strings, Breathy Winds, Brassy Bites
  // =========================================================================

  private scheduleMelodicNote(
    instName: string,
    freq: number,
    startTime: number,
    duration: number
  ) {
    if (!this.ctx || !this.compressor) return;

    const inst = (instName || 'Piano').toLowerCase();
    const now = this.ctx.currentTime;
    if (startTime + duration <= now) return;

    const safeStart = Math.max(now + 0.005, startTime);
    const safeDuration = Math.max(0.02, duration - (safeStart - startTime));

    // ----------------- VIOLIN & STRINGS -----------------
    if (inst.includes('violin') || (inst.includes('string') && !inst.includes('cello'))) {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(freq, safeStart);

      // Delayed vibrato (human bowed nuance)
      const lfo = this.ctx.createOscillator();
      const lfoGain = this.ctx.createGain();
      lfo.frequency.setValueAtTime(5.4, safeStart); // 5.4 Hz vibrato
      lfoGain.gain.setValueAtTime(0, safeStart);
      lfoGain.gain.linearRampToValueAtTime(5.5, safeStart + 0.12); // fade in vibrato
      lfo.connect(osc.frequency);

      // Wooden body formant resonance filter
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(2200, safeStart);
      filter.Q.setValueAtTime(2.0, safeStart);

      // Bowing attack & sustain
      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.24, safeStart + 0.04);
      gain.gain.setValueAtTime(0.22, safeStart + safeDuration * 0.85);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration + 0.04);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      osc.start(safeStart);
      lfo.start(safeStart);
      osc.stop(safeStart + safeDuration + 0.06);
      lfo.stop(safeStart + safeDuration + 0.06);

      this.activeOscillators.push(osc, lfo);
      this.activeGains.push(gain, lfoGain);
      return;
    }

    // ----------------- CELLO -----------------
    if (inst.includes('cello')) {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(freq, safeStart);

      const lfo = this.ctx.createOscillator();
      const lfoGain = this.ctx.createGain();
      lfo.frequency.setValueAtTime(4.6, safeStart);
      lfoGain.gain.setValueAtTime(0, safeStart);
      lfoGain.gain.linearRampToValueAtTime(4.0, safeStart + 0.15);
      lfo.connect(osc.frequency);

      // Deep resonant body filter
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(900, safeStart);
      filter.Q.setValueAtTime(2.2, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.32, safeStart + 0.055);
      gain.gain.setValueAtTime(0.28, safeStart + safeDuration * 0.85);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration + 0.05);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      osc.start(safeStart);
      lfo.start(safeStart);
      osc.stop(safeStart + safeDuration + 0.07);
      lfo.stop(safeStart + safeDuration + 0.07);

      this.activeOscillators.push(osc, lfo);
      this.activeGains.push(gain, lfoGain);
      return;
    }

    // ----------------- FLUTE (BREATHY WOODWIND) -----------------
    if (inst.includes('flute')) {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.25, safeStart + 0.04);
      gain.gain.setValueAtTime(0.22, safeStart + safeDuration * 0.85);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration + 0.03);

      osc.connect(gain);
      gain.connect(this.compressor);

      // Breathy airflow noise component
      let breathSource: AudioBufferSourceNode | null = null;
      let breathGain: GainNode | null = null;
      if (this.noiseBuffer) {
        breathSource = this.ctx.createBufferSource();
        breathSource.buffer = this.noiseBuffer;
        const breathFilter = this.ctx.createBiquadFilter();
        breathFilter.type = 'bandpass';
        breathFilter.frequency.setValueAtTime(Math.min(10000, freq * 1.5), safeStart);
        breathFilter.Q.setValueAtTime(5.0, safeStart);

        breathGain = this.ctx.createGain();
        breathGain.gain.setValueAtTime(0.0001, safeStart);
        breathGain.gain.linearRampToValueAtTime(0.04, safeStart + 0.04);
        breathGain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

        breathSource.connect(breathFilter);
        breathFilter.connect(breathGain);
        breathGain.connect(this.compressor);

        breathSource.start(safeStart);
        breathSource.stop(safeStart + safeDuration + 0.02);
        this.activeBufferSources.push(breathSource);
        this.activeGains.push(breathGain);
      }

      osc.start(safeStart);
      osc.stop(safeStart + safeDuration + 0.04);
      this.activeOscillators.push(osc);
      this.activeGains.push(gain);
      return;
    }

    // ----------------- TRUMPET & BRASS (BRIGHT LIP ATTACK) -----------------
    if (inst.includes('trumpet') || inst.includes('brass')) {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(freq, safeStart);

      // Dynamic lowpass filter envelope: starts dark, explodes on attack, then sustains
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(1100, safeStart);
      filter.frequency.linearRampToValueAtTime(3800, safeStart + 0.025);
      filter.frequency.exponentialRampToValueAtTime(2200, safeStart + safeDuration);
      filter.Q.setValueAtTime(2.5, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.26, safeStart + 0.025);
      gain.gain.setValueAtTime(0.24, safeStart + safeDuration * 0.85);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration + 0.02);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      osc.start(safeStart);
      osc.stop(safeStart + safeDuration + 0.03);
      this.activeOscillators.push(osc);
      this.activeGains.push(gain);
      return;
    }

    // ----------------- BASS (PUNCHY SUB & LOW-END) -----------------
    if (inst.includes('bass')) {
      // Fundamental Sine + Warm Triangle Sub
      const osc1 = this.ctx.createOscillator();
      const osc2 = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(freq, safeStart);

      osc2.type = 'triangle';
      osc2.frequency.setValueAtTime(freq, safeStart);

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(550, safeStart);
      filter.Q.setValueAtTime(1.2, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.40, safeStart + 0.008);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc1.connect(filter);
      osc2.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      osc1.start(safeStart);
      osc2.start(safeStart);
      osc1.stop(safeStart + safeDuration + 0.02);
      osc2.stop(safeStart + safeDuration + 0.02);

      this.activeOscillators.push(osc1, osc2);
      this.activeGains.push(gain);
      return;
    }

    // ----------------- GUITAR (PLUCKED STRING RESONANCE) -----------------
    if (inst.includes('guitar')) {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, safeStart);

      // Pluck filter: bright attack rapidly dampening to warm body
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(2800, safeStart);
      filter.frequency.exponentialRampToValueAtTime(700, safeStart + Math.min(0.25, safeDuration));

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.38, safeStart + 0.003);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      osc.start(safeStart);
      osc.stop(safeStart + safeDuration + 0.02);
      this.activeOscillators.push(osc);
      this.activeGains.push(gain);
      return;
    }

    // ----------------- ORGAN (DRAWBAR ADDITIVE SYNTHESIS) -----------------
    if (inst.includes('organ')) {
      // 3 Drawbars: 8' (1x), 4' (2x), 2-2/3' (3x)
      const osc8 = this.ctx.createOscillator();
      const osc4 = this.ctx.createOscillator();
      const osc2 = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc8.type = 'sine';
      osc8.frequency.setValueAtTime(freq, safeStart);

      osc4.type = 'sine';
      osc4.frequency.setValueAtTime(freq * 2, safeStart);

      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(freq * 3, safeStart);

      const subGain4 = this.ctx.createGain();
      subGain4.gain.setValueAtTime(0.5, safeStart);
      const subGain2 = this.ctx.createGain();
      subGain2.gain.setValueAtTime(0.3, safeStart);

      osc8.connect(gain);
      osc4.connect(subGain4);
      subGain4.connect(gain);
      osc2.connect(subGain2);
      subGain2.connect(gain);

      // Sustained organ envelope (organ pipes do not decay until released)
      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.22, safeStart + 0.015);
      gain.gain.setValueAtTime(0.22, safeStart + safeDuration);
      gain.gain.linearRampToValueAtTime(0.0001, safeStart + safeDuration + 0.03);

      gain.connect(this.compressor);

      osc8.start(safeStart);
      osc4.start(safeStart);
      osc2.start(safeStart);
      osc8.stop(safeStart + safeDuration + 0.04);
      osc4.stop(safeStart + safeDuration + 0.04);
      osc2.stop(safeStart + safeDuration + 0.04);

      this.activeOscillators.push(osc8, osc4, osc2);
      this.activeGains.push(gain, subGain4, subGain2);
      return;
    }

    // ----------------- SAXOPHONE & CLARINET (REEDS) -----------------
    if (inst.includes('saxophone') || inst.includes('sax') || inst.includes('clarinet')) {
      const isSax = inst.includes('sax');
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = isSax ? 'sawtooth' : 'square';
      osc.frequency.setValueAtTime(freq, safeStart);

      const filter = this.ctx.createBiquadFilter();
      filter.type = isSax ? 'bandpass' : 'lowpass';
      filter.frequency.setValueAtTime(isSax ? 1600 : 1900, safeStart);
      filter.Q.setValueAtTime(isSax ? 1.8 : 1.2, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.24, safeStart + 0.02);
      gain.gain.setValueAtTime(0.22, safeStart + safeDuration * 0.85);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration + 0.02);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      osc.start(safeStart);
      osc.stop(safeStart + safeDuration + 0.03);
      this.activeOscillators.push(osc);
      this.activeGains.push(gain);
      return;
    }

    // ----------------- SYNTH (LEAD PULSE) -----------------
    if (inst.includes('synth')) {
      const osc1 = this.ctx.createOscillator();
      const osc2 = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc1.type = 'sawtooth';
      osc1.frequency.setValueAtTime(freq, safeStart);
      osc2.type = 'sawtooth';
      osc2.frequency.setValueAtTime(freq * 1.004, safeStart); // slight chorused detune

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(2600, safeStart);
      filter.Q.setValueAtTime(3.0, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(0.25, safeStart + 0.008);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc1.connect(filter);
      osc2.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);

      osc1.start(safeStart);
      osc2.start(safeStart);
      osc1.stop(safeStart + safeDuration + 0.02);
      osc2.stop(safeStart + safeDuration + 0.02);

      this.activeOscillators.push(osc1, osc2);
      this.activeGains.push(gain);
      return;
    }

    // ----------------- ACOUSTIC PIANO (DEFAULT) -----------------
    // Dual triangle + subtle overtone with sharp percussive attack & acoustic decay
    const osc1 = this.ctx.createOscillator();
    const osc2 = this.ctx.createOscillator();
    const gain = this.ctx.createGain();

    osc1.type = 'triangle';
    osc1.frequency.setValueAtTime(freq, safeStart);

    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(freq * 2, safeStart);

    const overtoneGain = this.ctx.createGain();
    overtoneGain.gain.setValueAtTime(0.18, safeStart);

    osc1.connect(gain);
    osc2.connect(overtoneGain);
    overtoneGain.connect(gain);

    gain.gain.setValueAtTime(0.0001, safeStart);
    gain.gain.linearRampToValueAtTime(0.36, safeStart + 0.003); // Hammer strike
    gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

    gain.connect(this.compressor);

    osc1.start(safeStart);
    osc2.start(safeStart);
    osc1.stop(safeStart + safeDuration + 0.02);
    osc2.stop(safeStart + safeDuration + 0.02);

    this.activeOscillators.push(osc1, osc2);
    this.activeGains.push(gain, overtoneGain);
  }

  /**
   * Main note scheduler: routes to percussion model or melodic instrument model.
   */
  private scheduleNote(
    instName: string,
    freq: number,
    startTime: number,
    duration: number,
    midiNumber?: number,
    noteName?: string,
    channel?: number
  ) {
    const inst = (instName || 'Piano').toLowerCase();
    const isPercussion =
      channel === 9 ||
      inst.includes('drum') ||
      inst.includes('percussion') ||
      (noteName && (
        noteName.toLowerCase().includes('kick') ||
        noteName.toLowerCase().includes('snare') ||
        noteName.toLowerCase().includes('hi-hat') ||
        noteName.toLowerCase().includes('hihat') ||
        noteName.toLowerCase().includes('clap') ||
        noteName.toLowerCase().includes('tom') ||
        noteName.toLowerCase().includes('crash') ||
        noteName.toLowerCase().includes('ride')
      ));

    if (isPercussion) {
      this.scheduleDrum(midiNumber || 36, noteName || '', startTime, duration);
    } else {
      this.scheduleMelodicNote(instName, freq, startTime, duration);
    }
  }

  /**
   * Starts playback of a synchronized timeline from an optional start offset in seconds.
   */
  public play(
    timeline: NoteTimelineEvent[],
    startOffsetSec: number = 0,
    onProgress?: (progress: number, currentTime: number, totalTime: number) => void,
    onEnded?: () => void
  ) {
    this.stopPlaybackNodes();
    this.initAudio();
    if (!this.ctx) return;

    this.currentTimeline = timeline;
    this.onProgressCallback = onProgress;
    this.onEndedCallback = onEnded;

    const notes = timeline.filter((e) => e.kind === 'PLAY' && e.midi_number !== undefined);
    if (notes.length === 0) {
      if (onEnded) onEnded();
      return;
    }

    // Determine accurate total duration
    let maxEnd = 0;
    for (const n of notes) {
      const start = n.start_sec !== undefined ? n.start_sec : (n.start_beat || 0) * (60.0 / (n.bpm || 120));
      const dur = n.duration_sec !== undefined ? n.duration_sec : (n.beats || 1.0) * (60.0 / (n.bpm || 120));
      if (start + dur > maxEnd) {
        maxEnd = start + dur;
      }
    }
    this.totalDurationSec = Math.max(0.1, maxEnd);

    // If offset is beyond end, wrap to start
    const offset = startOffsetSec >= this.totalDurationSec ? 0 : Math.max(0, startOffsetSec);
    this.currentOffsetSec = offset;

    const baseAudioTime = this.ctx.currentTime + 0.04;
    this.playbackStartAudioTime = baseAudioTime;
    this.state = 'playing';
    if (this.onStateChangeCallback) this.onStateChangeCallback('playing');

    // Schedule all notes using absolute musical event times converted to audio-context time
    for (const n of notes) {
      const noteStartSec = n.start_sec !== undefined ? n.start_sec : (n.start_beat || 0) * (60.0 / (n.bpm || 120));
      const noteDurSec = n.duration_sec !== undefined ? n.duration_sec : (n.beats || 1.0) * (60.0 / (n.bpm || 120));
      const noteEndSec = noteStartSec + noteDurSec;

      // Note has already completed before current offset
      if (noteEndSec <= offset) continue;

      const scheduledAudioStart = baseAudioTime + Math.max(0, noteStartSec - offset);
      const effectiveDuration = noteStartSec < offset ? noteEndSec - offset : noteDurSec;
      const freq = this.midiToFrequency(n.midi_number!);

      this.scheduleNote(
        n.instrument || 'Piano',
        freq,
        scheduledAudioStart,
        effectiveDuration,
        n.midi_number,
        n.note,
        n.channel
      );
    }

    // High precision requestAnimationFrame progress loop
    this.startProgressLoop();
  }

  public pause() {
    if (this.state !== 'playing' || !this.ctx) return;
    const elapsed = (this.ctx.currentTime - this.playbackStartAudioTime) + this.currentOffsetSec;
    this.currentOffsetSec = Math.max(0, Math.min(this.totalDurationSec, elapsed));
    this.stopPlaybackNodes();
    this.state = 'paused';
    if (this.onStateChangeCallback) this.onStateChangeCallback('paused');

    if (this.onProgressCallback) {
      const progress = this.totalDurationSec > 0 ? this.currentOffsetSec / this.totalDurationSec : 0;
      this.onProgressCallback(progress, this.currentOffsetSec, this.totalDurationSec);
    }
  }

  public resume() {
    if (this.state === 'paused' && this.currentTimeline.length > 0) {
      this.play(this.currentTimeline, this.currentOffsetSec, this.onProgressCallback, this.onEndedCallback);
    }
  }

  public seek(targetProgress: number) {
    const clampedProgress = Math.max(0, Math.min(1, targetProgress));
    const targetSec = clampedProgress * this.totalDurationSec;
    const wasPlaying = this.state === 'playing';

    if (wasPlaying) {
      this.play(this.currentTimeline, targetSec, this.onProgressCallback, this.onEndedCallback);
    } else {
      this.currentOffsetSec = targetSec;
      if (this.onProgressCallback) {
        this.onProgressCallback(clampedProgress, targetSec, this.totalDurationSec);
      }
    }
  }

  public stop() {
    this.stopPlaybackNodes();
    this.currentOffsetSec = 0;
    this.state = 'stopped';
    if (this.onStateChangeCallback) this.onStateChangeCallback('stopped');

    if (this.onProgressCallback) {
      this.onProgressCallback(0, 0, this.totalDurationSec);
    }
  }

  private stopPlaybackNodes() {
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }

    for (const osc of this.activeOscillators) {
      try {
        osc.stop();
        osc.disconnect();
      } catch {}
    }
    for (const src of this.activeBufferSources) {
      try {
        src.stop();
        src.disconnect();
      } catch {}
    }
    for (const g of this.activeGains) {
      try {
        g.disconnect();
      } catch {}
    }
    this.activeOscillators = [];
    this.activeBufferSources = [];
    this.activeGains = [];
  }

  private startProgressLoop() {
    const update = () => {
      if (this.state !== 'playing' || !this.ctx) return;

      const elapsed = (this.ctx.currentTime - this.playbackStartAudioTime) + this.currentOffsetSec;
      const clampedCurrent = Math.max(0, Math.min(this.totalDurationSec, elapsed));
      const progress = this.totalDurationSec > 0 ? clampedCurrent / this.totalDurationSec : 0;

      if (this.onProgressCallback) {
        this.onProgressCallback(progress, clampedCurrent, this.totalDurationSec);
      }

      if (elapsed >= this.totalDurationSec) {
        this.stop();
        if (this.onEndedCallback) {
          this.onEndedCallback();
        }
        return;
      }

      this.rafId = window.requestAnimationFrame(update);
    };

    this.rafId = window.requestAnimationFrame(update);
  }
}

export const globalSynth = new SymphonySynth();
