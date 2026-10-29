import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Play,
  Pause,
  Square,
  RotateCcw,
  Download,
  Volume2,
  CheckCircle2,
  Music,
} from 'lucide-react';
import { globalSynth, type NoteTimelineEvent, type PlaybackState } from '../audio/synth';

interface AudioPlayerProps {
  messageId: string;
  timeline?: NoteTimelineEvent[];
  tracks?: string[];
  totalDurationSec?: number;
  bpm?: number;
  midiUrl?: string;
  activePlayingId: string | null;
  setActivePlayingId: (id: string | null) => void;
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  messageId,
  timeline,
  tracks,
  totalDurationSec = 0,
  bpm = 120,
  midiUrl,
  activePlayingId,
  setActivePlayingId,
}) => {
  const [playbackState, setPlaybackState] = useState<PlaybackState>('stopped');
  const [isHoveringBar, setIsHoveringBar] = useState(false);

  // References for direct DOM updates (smooth 60fps without React re-renders)
  const progressBarRef = useRef<HTMLDivElement>(null);
  const progressFillRef = useRef<HTMLDivElement>(null);
  const progressThumbRef = useRef<HTMLDivElement>(null);
  const currentTimeLabelRef = useRef<HTMLSpanElement>(null);
  const totalTimeLabelRef = useRef<HTMLSpanElement>(null);

  const isCurrentActive = activePlayingId === messageId;

  // Calculate actual total duration
  const derivedTotalDuration = React.useMemo(() => {
    if (totalDurationSec && totalDurationSec > 0) return totalDurationSec;
    if (!timeline || timeline.length === 0) return 0;
    let maxEnd = 0;
    for (const e of timeline) {
      const start = e.start_sec !== undefined ? e.start_sec : (e.start_beat || 0) * (60.0 / (e.bpm || bpm || 120));
      const dur = e.duration_sec !== undefined ? e.duration_sec : (e.beats || 1.0) * (60.0 / (e.bpm || bpm || 120));
      if (start + dur > maxEnd) maxEnd = start + dur;
    }
    return Math.max(0.1, maxEnd);
  }, [totalDurationSec, timeline, bpm]);

  const formatTime = (seconds: number) => {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const remSec = s % 60;
    return `${m}:${remSec < 10 ? '0' : ''}${remSec}`;
  };

  const updateVisualProgress = useCallback((progress: number, currentTime: number, totalTime: number) => {
    const clampedProgress = Math.max(0, Math.min(1, progress));
    if (progressFillRef.current) {
      progressFillRef.current.style.width = `${clampedProgress * 100}%`;
    }
    if (progressThumbRef.current) {
      progressThumbRef.current.style.left = `${clampedProgress * 100}%`;
    }
    if (currentTimeLabelRef.current) {
      currentTimeLabelRef.current.textContent = formatTime(currentTime);
    }
    if (totalTimeLabelRef.current) {
      totalTimeLabelRef.current.textContent = formatTime(totalTime);
    }
  }, []);

  // Reset visual progress if another audio player starts
  useEffect(() => {
    if (!isCurrentActive) {
      setPlaybackState((prev) => {
        if (prev !== 'stopped') {
          updateVisualProgress(0, 0, derivedTotalDuration);
          return 'stopped';
        }
        return prev;
      });
    }
  }, [isCurrentActive, derivedTotalDuration, updateVisualProgress]);

  // Set initial duration on mount
  useEffect(() => {
    if (totalTimeLabelRef.current) {
      totalTimeLabelRef.current.textContent = formatTime(derivedTotalDuration);
    }
  }, [derivedTotalDuration]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (isCurrentActive) {
        globalSynth.stop();
      }
    };
  }, [isCurrentActive]);

  const handlePlay = () => {
    if (!timeline || timeline.length === 0) return;

    if (playbackState === 'paused' && isCurrentActive) {
      globalSynth.resume();
      setPlaybackState('playing');
      return;
    }

    setActivePlayingId(messageId);
    setPlaybackState('playing');

    globalSynth.play(
      timeline,
      0,
      (progress, current, total) => {
        updateVisualProgress(progress, current, total);
      },
      () => {
        setPlaybackState('stopped');
        setActivePlayingId(null);
        updateVisualProgress(0, 0, derivedTotalDuration);
      }
    );
  };

  const handlePause = () => {
    globalSynth.pause();
    setPlaybackState('paused');
  };

  const handleStop = () => {
    globalSynth.stop();
    setPlaybackState('stopped');
    setActivePlayingId(null);
    updateVisualProgress(0, 0, derivedTotalDuration);
  };

  const handleReplay = () => {
    handleStop();
    setTimeout(() => {
      handlePlay();
    }, 40);
  };

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!progressBarRef.current || derivedTotalDuration <= 0) return;
    const rect = progressBarRef.current.getBoundingClientRect();
    const clickX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    const ratio = clickX / rect.width;

    if (!isCurrentActive) {
      setActivePlayingId(messageId);
    }

    if (playbackState === 'playing') {
      globalSynth.seek(ratio);
    } else {
      updateVisualProgress(ratio, ratio * derivedTotalDuration, derivedTotalDuration);
      if (timeline) {
        setPlaybackState('playing');
        globalSynth.play(
          timeline,
          ratio * derivedTotalDuration,
          (prog, cur, tot) => {
            updateVisualProgress(prog, cur, tot);
          },
          () => {
            setPlaybackState('stopped');
            setActivePlayingId(null);
            updateVisualProgress(0, 0, derivedTotalDuration);
          }
        );
      }
    }
  };

  // Distinct list of instruments from timeline
  const uniqueInstruments = React.useMemo(() => {
    if (!timeline) return [];
    const set = new Set<string>();
    for (const e of timeline) {
      if (e.instrument) set.add(e.instrument);
    }
    return Array.from(set);
  }, [timeline]);

  return (
    <div className="w-full rounded-2xl border border-zinc-700/80 bg-[#252528] p-4 shadow-xl space-y-3.5 transition-all">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-emerald-500/20 to-teal-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0">
            <Volume2 className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-white tracking-wide">
                {playbackState === 'playing'
                  ? 'Playing Audio Preview'
                  : playbackState === 'paused'
                  ? 'Playback Paused'
                  : 'Studio Playback Ready'}
              </span>
              <span className="text-[10px] bg-emerald-500/15 text-emerald-300 font-medium px-2 py-0.5 rounded-full border border-emerald-500/30 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                Synchronized
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-[11px] text-zinc-400">
              <span>{bpm} BPM</span>
              <span>•</span>
              <span className="truncate max-w-[200px] sm:max-w-xs">
                {uniqueInstruments.length > 0
                  ? uniqueInstruments.join(', ')
                  : tracks?.join(', ') || 'General MIDI'}
              </span>
            </div>
          </div>
        </div>

        {/* MIDI Download Button */}
        {midiUrl && (
          <a
            href={midiUrl}
            download="symphony.mid"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 hover:text-white text-xs font-medium border border-zinc-700 transition-colors shadow-sm"
            title="Download standard General MIDI file"
          >
            <Download className="h-3.5 w-3.5 text-emerald-400" />
            <span>Download MIDI</span>
          </a>
        )}
      </div>

      {/* Progress Bar & Seek Area */}
      <div className="space-y-1.5 pt-1">
        <div
          ref={progressBarRef}
          onClick={handleSeek}
          onMouseEnter={() => setIsHoveringBar(true)}
          onMouseLeave={() => setIsHoveringBar(false)}
          className="relative w-full h-4 flex items-center cursor-pointer select-none group"
        >
          {/* Background Track */}
          <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden transition-all group-hover:h-2">
            {/* Active Progress Fill */}
            <div
              ref={progressFillRef}
              className="h-full bg-gradient-to-r from-emerald-400 to-teal-400 rounded-full w-0"
            />
          </div>

          {/* Interactive Scrub Thumb */}
          <div
            ref={progressThumbRef}
            className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-white rounded-full shadow-lg border border-zinc-300 pointer-events-none transition-opacity ${
              isHoveringBar || playbackState === 'playing' ? 'opacity-100 scale-100' : 'opacity-0 scale-75'
            }`}
            style={{ left: '0%' }}
          />
        </div>

        {/* Timestamps */}
        <div className="flex justify-between items-center text-[10px] text-zinc-400 font-mono tracking-wider">
          <span ref={currentTimeLabelRef}>0:00</span>
          <span ref={totalTimeLabelRef}>{formatTime(derivedTotalDuration)}</span>
        </div>
      </div>

      {/* Audio Controls Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-zinc-800/80">
        <div className="flex items-center gap-1.5">
          {playbackState === 'playing' ? (
            <button
              onClick={handlePause}
              className="h-8 px-3 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs flex items-center gap-1.5 transition-colors shadow-sm"
              title="Pause playback"
            >
              <Pause className="h-3.5 w-3.5 fill-current" />
              <span>Pause</span>
            </button>
          ) : (
            <button
              onClick={handlePlay}
              className="h-8 px-3.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs flex items-center gap-1.5 transition-colors shadow-sm"
              title="Play composition"
            >
              <Play className="h-3.5 w-3.5 fill-current ml-0.5" />
              <span>Play</span>
            </button>
          )}

          <button
            onClick={handleStop}
            disabled={playbackState === 'stopped'}
            className="h-8 px-2.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 disabled:opacity-40 disabled:hover:bg-transparent transition-colors flex items-center gap-1 text-xs"
            title="Stop playback"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
            <span className="hidden sm:inline">Stop</span>
          </button>

          <button
            onClick={handleReplay}
            className="h-8 px-2.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors flex items-center gap-1 text-xs"
            title="Restart from beginning"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Replay</span>
          </button>
        </div>

        <div className="text-[11px] text-zinc-500 hidden sm:flex items-center gap-1">
          <Music className="h-3 w-3 text-zinc-500" />
          <span>Shared Web Audio Timeline</span>
        </div>
      </div>
    </div>
  );
};

