/**
 * synth.ts
 * High-fidelity, synchronized Web Audio API synthesizer for SymphonyLang Studio.
 * Uses sample-accurate AudioContext look-ahead scheduling, instrument-specific timbres,
 * and a master dynamics compressor for polyphonic multi-instrument playback.
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
  private activeOscillators: OscillatorNode[] = [];
  private activeGains: GainNode[] = [];

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
    }

    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
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

  /**
   * Schedules note synthesis with exact acoustic modeling per instrument.
   */
  private scheduleNote(
    instName: string,
    freq: number,
    startTime: number,
    duration: number
  ) {
    if (!this.ctx || !this.compressor) return;

    const inst = (instName || 'Piano').toLowerCase();
    const now = this.ctx.currentTime;
    // Skip if note already finished in the past
    if (startTime + duration <= now) return;

    const safeStart = Math.max(now + 0.005, startTime);
    const safeDuration = Math.max(0.02, duration - (safeStart - startTime));

    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();

    // Default envelope parameters
    let attack = 0.01;
    let peakVolume = 0.28;
    let waveType: OscillatorType = 'triangle';

    if (inst.includes('flute')) {
      waveType = 'sine';
      attack = 0.04;
      peakVolume = 0.22;
      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(gain);
      gain.connect(this.compressor);
    } else if (
      inst.includes('violin') ||
      inst.includes('cello') ||
      inst.includes('strings')
    ) {
      waveType = 'sawtooth';
      attack = inst.includes('cello') ? 0.05 : 0.035;
      peakVolume = inst.includes('cello') ? 0.26 : 0.20;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      // Lowpass body filter for warm bowed sound
      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(
        inst.includes('cello') ? 950 : 1800,
        safeStart
      );

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);
    } else if (inst.includes('trumpet') || inst.includes('brass')) {
      waveType = 'sawtooth';
      attack = 0.02;
      peakVolume = 0.22;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      // Brass filter opens on onset
      filter.frequency.setValueAtTime(1200, safeStart);
      filter.frequency.linearRampToValueAtTime(3200, safeStart + attack);
      filter.frequency.exponentialRampToValueAtTime(1400, safeStart + safeDuration);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);
    } else if (inst.includes('clarinet')) {
      waveType = 'square';
      attack = 0.025;
      peakVolume = 0.18;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(2000, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);
    } else if (inst.includes('saxophone') || inst.includes('sax')) {
      waveType = 'sawtooth';
      attack = 0.025;
      peakVolume = 0.22;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.setValueAtTime(1500, safeStart);
      filter.Q.setValueAtTime(1.5, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);
    } else if (inst.includes('synth')) {
      waveType = 'sawtooth';
      attack = 0.008;
      peakVolume = 0.22;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(gain);
      gain.connect(this.compressor);
    } else if (inst.includes('bass')) {
      waveType = 'triangle';
      attack = 0.015;
      peakVolume = 0.32;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(600, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);
    } else if (inst.includes('guitar')) {
      waveType = 'triangle';
      attack = 0.005;
      peakVolume = 0.30;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(gain);
      gain.connect(this.compressor);
    } else if (inst.includes('organ')) {
      waveType = 'square';
      attack = 0.01;
      peakVolume = 0.16;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      const filter = this.ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(2200, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.compressor);
    } else {
      // Default Piano
      waveType = 'triangle';
      attack = 0.008;
      peakVolume = 0.32;

      osc.type = waveType;
      osc.frequency.setValueAtTime(freq, safeStart);

      gain.gain.setValueAtTime(0.0001, safeStart);
      gain.gain.linearRampToValueAtTime(peakVolume, safeStart + attack);
      gain.gain.exponentialRampToValueAtTime(0.0001, safeStart + safeDuration);

      osc.connect(gain);
      gain.connect(this.compressor);
    }

    try {
      osc.start(safeStart);
      osc.stop(safeStart + safeDuration + 0.02);
      this.activeOscillators.push(osc);
      this.activeGains.push(gain);
    } catch {
      // Ignore if past window
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

      this.scheduleNote(n.instrument || 'Piano', freq, scheduledAudioStart, effectiveDuration);
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
    for (const g of this.activeGains) {
      try {
        g.disconnect();
      } catch {}
    }
    this.activeOscillators = [];
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
      } else {
        this.rafId = window.requestAnimationFrame(update);
      }
    };

    this.rafId = window.requestAnimationFrame(update);
  }
}

export const globalSynth = new SymphonySynth();
