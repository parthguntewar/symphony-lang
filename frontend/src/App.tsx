import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Sparkles,
  Music,
  Download,
  Copy,
  Check,
  Send,
  Plus,
  Trash2,
  AlertCircle,
  Code2,
  Sliders,
  RefreshCw,
  Terminal,
  ChevronDown,
  ChevronUp,
  Settings,
  HelpCircle,
  Menu,
  X,
} from 'lucide-react';
import { globalSynth, type NoteTimelineEvent } from './audio/synth';
import { AudioPlayer } from './components/AudioPlayer';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  code?: string;
  isTemplateFallback?: boolean;
  provider?: string;
  compilation?: {
    status: 'idle' | 'compiling' | 'success' | 'error';
    output?: string;
    errors?: string[];
    midiId?: string;
    midiUrl?: string;
    tracks?: string[];
    timeline?: NoteTimelineEvent[];
    totalDurationSec?: number;
    bpm?: number;
  };
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
}

interface BackendHealth {
  status: string;
  has_llm_key: boolean;
  active_provider: string | null;
  supported_instruments: string[];
}

const EXAMPLE_PROMPTS = [
  {
    title: 'Cheerful Piano Melody',
    prompt: 'Create a cheerful piano melody.',
    subtitle: 'Bright C major arpeggio with buoyant cadence',
  },
  {
    title: 'Calm Ambient Soundtrack',
    prompt: 'Compose a calm ambient soundtrack.',
    subtitle: 'Atmospheric multi-track harmony with Flute and Cello',
  },
  {
    title: 'Energetic Melody at 120 BPM',
    prompt: 'Create an energetic melody at 120 BPM.',
    subtitle: 'Driving 16th-note synth pulse with function motifs',
  },
];

export default function App() {
  const [chats, setChats] = useState<ChatSession[]>(() => {
    try {
      const saved = localStorage.getItem('symphonylang_chats');
      if (saved) return JSON.parse(saved);
    } catch {}
    return [
      {
        id: 'default',
        title: 'New Composition',
        messages: [],
        updatedAt: Date.now(),
      },
    ];
  });

  const [activeChatId, setActiveChatId] = useState<string>('default');
  const [inputPrompt, setInputPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [copiedCodeId, setCopiedCodeId] = useState<string | null>(null);
  const [expandedOutputId, setExpandedOutputId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showDocsModal, setShowDocsModal] = useState(false);

  // Active playback state
  const [activePlayingId, setActivePlayingId] = useState<string | null>(null);

  // Backend health & active provider
  const [health, setHealth] = useState<BackendHealth | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const activeChat = chats.find((c) => c.id === activeChatId) || chats[0];

  // Persist chats
  useEffect(() => {
    try {
      localStorage.setItem('symphonylang_chats', JSON.stringify(chats));
    } catch {}
  }, [chats]);

  // Fetch health on mount
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        setHealth(data);
      }
    } catch (err) {
      console.warn('Backend connection pending:', err);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeChat?.messages, isGenerating]);

  // Adjust textarea height automatically
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputPrompt(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  };

  const createNewChat = () => {
    globalSynth.stop();
    setActivePlayingId(null);
    const newChat: ChatSession = {
      id: Date.now().toString(),
      title: 'New Composition',
      messages: [],
      updatedAt: Date.now(),
    };
    setChats((prev) => [newChat, ...prev]);
    setActiveChatId(newChat.id);
    setInputPrompt('');
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  };

  const deleteChat = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (chats.length <= 1) {
      createNewChat();
      return;
    }
    const filtered = chats.filter((c) => c.id !== id);
    setChats(filtered);
    if (activeChatId === id) {
      setActiveChatId(filtered[0].id);
    }
  };

  const handleSend = async (overridePrompt?: string) => {
    const promptToSend = (overridePrompt || inputPrompt).trim();
    if (!promptToSend || isGenerating) return;

    setInputPrompt('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    const userMsgId = Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();

    const userMessage: Message = {
      id: userMsgId,
      role: 'user',
      content: promptToSend,
    };

    // Placeholder assistant message
    const assistantMessage: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      compilation: {
        status: 'idle',
      },
    };

    // Update active chat title if first message
    const newTitle =
      activeChat.messages.length === 0
        ? promptToSend.slice(0, 30) + (promptToSend.length > 30 ? '...' : '')
        : activeChat.title;

    setChats((prev) =>
      prev.map((c) => {
        if (c.id === activeChatId) {
          return {
            ...c,
            title: newTitle,
            updatedAt: Date.now(),
            messages: [...c.messages, userMessage, assistantMessage],
          };
        }
        return c;
      })
    );

    setIsGenerating(true);

    try {
      // Find the most recent code in the conversation to support modification requests
      const lastCode = activeChat.messages
        .slice()
        .reverse()
        .find((m) => m.code)?.code;

      const genRes = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: promptToSend,
          previous_code: lastCode,
        }),
      });

      if (!genRes.ok) {
        throw new Error(`Generation failed: ${genRes.statusText}`);
      }

      const genData = await genRes.json();
      const generatedCode: string = genData.code;
      const explanation: string = genData.explanation;
      const isComposition: boolean = !!genData.is_composition && !!generatedCode;

      if (!isComposition) {
        // Conversational response (greeting, polite redirection, or limitation note) - no compilation
        setChats((prev) =>
          prev.map((c) => {
            if (c.id === activeChatId) {
              const updated = c.messages.map((m) => {
                if (m.id === assistantMsgId) {
                  return {
                    ...m,
                    content: explanation,
                    code: undefined,
                    compilation: undefined,
                    provider: genData.provider,
                    isTemplateFallback: genData.is_template_fallback,
                  };
                }
                return m;
              });
              return { ...c, messages: updated };
            }
            return c;
          })
        );
        return;
      }

      // Update assistant message with generated code
      setChats((prev) =>
        prev.map((c) => {
          if (c.id === activeChatId) {
            const updated = c.messages.map((m) => {
              if (m.id === assistantMsgId) {
                return {
                  ...m,
                  content: explanation,
                  code: generatedCode,
                  isTemplateFallback: genData.is_template_fallback,
                  provider: genData.provider,
                  compilation: {
                    status: 'compiling' as const,
                  },
                };
              }
              return m;
            });
            return { ...c, messages: updated };
          }
          return c;
        })
      );

      // Immediately compile the generated code
      await triggerCompilation(assistantMsgId, generatedCode);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown generation error occurred.';
      setChats((prev) =>
        prev.map((c) => {
          if (c.id === activeChatId) {
            const updated = c.messages.map((m) => {
              if (m.id === assistantMsgId) {
                return {
                  ...m,
                  content: `Failed to generate SymphonyLang music: ${errorMessage}`,
                  compilation: {
                    status: 'error' as const,
                    errors: [errorMessage],
                  },
                };
              }
              return m;
            });
            return { ...c, messages: updated };
          }
          return c;
        })
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const triggerCompilation = async (messageId: string, codeToCompile: string) => {
    setChats((prev) =>
      prev.map((c) => {
        if (c.id === activeChatId) {
          const updated = c.messages.map((m) => {
            if (m.id === messageId) {
              return {
                ...m,
                compilation: {
                  status: 'compiling' as const,
                },
              };
            }
            return m;
          });
          return { ...c, messages: updated };
        }
        return c;
      })
    );

    try {
      const res = await fetch('/api/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_code: codeToCompile }),
      });

      const data = await res.json();

      setChats((prev) =>
        prev.map((c) => {
          if (c.id === activeChatId) {
            const updated = c.messages.map((m) => {
              if (m.id === messageId) {
                return {
                  ...m,
                  compilation: {
                    status: data.success ? ('success' as const) : ('error' as const),
                    output: data.compilation_output,
                    errors: data.errors,
                    midiId: data.midi_id,
                    midiUrl: data.midi_url,
                    tracks: data.tracks,
                    timeline: data.timeline,
                    totalDurationSec: data.total_duration_sec,
                    bpm: data.bpm,
                  },
                };
              }
              return m;
            });
            return { ...c, messages: updated };
          }
          return c;
        })
      );
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Compilation request failed.';
      setChats((prev) =>
        prev.map((c) => {
          if (c.id === activeChatId) {
            const updated = c.messages.map((m) => {
              if (m.id === messageId) {
                return {
                  ...m,
                  compilation: {
                    status: 'error' as const,
                    output: 'Failed to contact compiler server.',
                    errors: [errorMessage],
                  },
                };
              }
              return m;
            });
            return { ...c, messages: updated };
          }
          return c;
        })
      );
    }
  };

  const handleCopyCode = (id: string, code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCodeId(id);
    setTimeout(() => setCopiedCodeId(null), 2000);
  };

  const handleDownloadSource = (code: string) => {
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'composition.sym';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };



  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#212121] text-[#ececec] font-sans antialiased">
      {/* ----------------- SIDEBAR ----------------- */}
      <aside
        className={`${
          isSidebarOpen ? 'w-64 translate-x-0' : 'w-0 -translate-x-full md:w-0'
        } transition-all duration-200 ease-in-out flex flex-col bg-[#171717] border-r border-[#2b2b2b] shrink-0 z-30 select-none overflow-hidden`}
      >
        <div className="p-3 flex items-center justify-between border-b border-[#262626]">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-md">
              <Music className="h-4 w-4 text-white" />
            </div>
            <div>
              <h1 className="font-semibold text-sm tracking-wide text-white flex items-center gap-1.5">
                SymphonyLang
                <span className="text-[10px] bg-purple-500/20 text-purple-300 font-mono px-1.5 py-0.5 rounded border border-purple-500/30">
                  v1.0
                </span>
              </h1>
              <p className="text-[11px] text-zinc-400">AI Music Studio</p>
            </div>
          </div>
          <button
            onClick={() => setIsSidebarOpen(false)}
            className="md:hidden text-zinc-400 hover:text-white p-1 rounded-md"
            title="Close sidebar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-3">
          <button
            onClick={createNewChat}
            className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl border border-zinc-700/60 hover:bg-[#262626] text-sm text-zinc-200 transition-colors shadow-sm group"
          >
            <span className="flex items-center gap-2 font-medium">
              <Plus className="h-4 w-4 text-zinc-400 group-hover:text-white" />
              New composition
            </span>
            <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded border border-zinc-700">
              Ctrl+K
            </span>
          </button>
        </div>

        {/* Recent Conversations */}
        <div className="flex-1 overflow-y-auto px-3 py-1 space-y-1">
          <div className="px-2 pb-1.5 text-[11px] font-medium tracking-wider text-zinc-500 uppercase">
            Recent chats
          </div>
          {chats.map((chat) => (
            <div
              key={chat.id}
              onClick={() => {
                setActiveChatId(chat.id);
                if (window.innerWidth < 768) setIsSidebarOpen(false);
              }}
              className={`group flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition-colors ${
                chat.id === activeChatId
                  ? 'bg-[#262626] text-white font-medium'
                  : 'text-zinc-400 hover:bg-[#1f1f1f] hover:text-zinc-200'
              }`}
            >
              <div className="flex items-center gap-2.5 truncate pr-2">
                <Terminal className="h-3.5 w-3.5 shrink-0 opacity-70" />
                <span className="truncate">{chat.title || 'Untitled'}</span>
              </div>
              <button
                onClick={(e) => deleteChat(chat.id, e)}
                className="opacity-0 group-hover:opacity-100 hover:text-red-400 p-0.5 rounded transition-opacity"
                title="Delete chat"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-[#262626] space-y-1 bg-[#141414]">
          <button
            onClick={() => setShowDocsModal(true)}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs text-zinc-400 hover:text-white hover:bg-[#202020] transition-colors"
          >
            <HelpCircle className="h-4 w-4" />
            <span>SymphonyLang Syntax</span>
          </button>
          <button
            onClick={() => setShowSettingsModal(true)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs text-zinc-400 hover:text-white hover:bg-[#202020] transition-colors"
          >
            <div className="flex items-center gap-2.5">
              <Settings className="h-4 w-4" />
              <span>Engine Status</span>
            </div>
            <span
              className={`h-2 w-2 rounded-full ${
                health?.has_llm_key ? 'bg-emerald-400' : 'bg-amber-400'
              }`}
              title={health?.has_llm_key ? 'LLM Connected' : 'Fallback Engine Active'}
            />
          </button>
        </div>
      </aside>

      {/* ----------------- MAIN CHAT AREA ----------------- */}
      <main className="flex-1 flex flex-col h-full bg-[#212121] relative overflow-hidden">
        {/* Top Header Bar */}
        <header className="h-14 border-b border-[#2d2d2d] flex items-center justify-between px-4 shrink-0 bg-[#212121]/90 backdrop-blur z-20">
          <div className="flex items-center gap-3">
            {!isSidebarOpen && (
              <button
                onClick={() => setIsSidebarOpen(true)}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-[#2e2e2e] transition-colors"
                title="Open sidebar"
              >
                <Menu className="h-5 w-5" />
              </button>
            )}
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm text-zinc-200 tracking-wide">
                {activeChat.title}
              </span>
              <span className="text-[11px] text-zinc-400 border border-zinc-700 bg-zinc-800/80 px-2 py-0.5 rounded-full flex items-center gap-1.5">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    health?.has_llm_key ? 'bg-emerald-400' : 'bg-amber-400'
                  }`}
                />
                {health?.active_provider || 'Built-in Composition Engine'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={createNewChat}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-zinc-300 hover:text-white hover:bg-[#2e2e2e] border border-zinc-700/80 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New</span>
            </button>
          </div>
        </header>

        {/* Message Container / Welcome Screen */}
        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 space-y-6">
          {activeChat.messages.length === 0 ? (
            /* Welcome Screen */
            <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center px-4 -mt-8">
              <div className="h-16 w-16 rounded-2xl bg-gradient-to-tr from-purple-600 via-indigo-600 to-blue-500 flex items-center justify-center shadow-xl shadow-purple-500/10 mb-6">
                <Music className="h-8 w-8 text-white" />
              </div>
              <h2 className="text-3xl font-bold tracking-tight text-white mb-2">
                Make music with code.
              </h2>
              <p className="text-zinc-400 text-sm md:text-base max-w-md mx-auto mb-8 leading-relaxed">
                Describe the music you imagine. SymphonyLang will turn it into playable code.
              </p>

              {/* Three Clickable Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 w-full">
                {EXAMPLE_PROMPTS.map((eg, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(eg.prompt)}
                    className="flex flex-col text-left p-4 rounded-xl border border-zinc-800 bg-[#282828] hover:bg-[#2f2f2f] hover:border-zinc-700 transition-all text-xs group cursor-pointer shadow-sm"
                  >
                    <span className="font-medium text-zinc-200 group-hover:text-purple-300 transition-colors flex items-center justify-between mb-1">
                      {eg.title}
                      <Sparkles className="h-3.5 w-3.5 text-zinc-500 group-hover:text-purple-400" />
                    </span>
                    <span className="text-[11px] text-zinc-400 line-clamp-2">
                      "{eg.prompt}"
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Conversation Stream */
            <div className="max-w-3xl mx-auto space-y-6 pb-52 md:pb-60">
              {activeChat.messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${
                    msg.role === 'user' ? 'items-end' : 'items-start'
                  } group`}
                >
                  {/* User Message */}
                  {msg.role === 'user' ? (
                    <div className="flex items-start gap-3 max-w-[85%]">
                      <div className="bg-[#2f2f2f] text-zinc-100 px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm border border-zinc-700/60 shadow-sm leading-relaxed">
                        {msg.content}
                      </div>
                    </div>
                  ) : (
                    /* Assistant Message */
                    <div className="w-full flex items-start gap-3.5">
                      <div className="h-7 w-7 rounded-lg bg-gradient-to-tr from-purple-500 to-indigo-600 flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
                        <Sparkles className="h-3.5 w-3.5 text-white" />
                      </div>

                      <div className="flex-1 space-y-3 min-w-0">
                        {/* Loading pulse if no content yet */}
                        {!msg.content && !msg.code && (
                          <div className="flex items-center gap-2 text-xs text-zinc-400 py-2">
                            <RefreshCw className="h-3.5 w-3.5 animate-spin text-purple-400" />
                            <span>Composing SymphonyLang program...</span>
                          </div>
                        )}

                        {/* Explanation Text */}
                        {msg.content && (
                          <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-line">
                            {msg.content}
                          </div>
                        )}

                        {/* Generated Code Block */}
                        {msg.code && (
                          <div className="rounded-xl border border-zinc-700/80 bg-[#18181b] overflow-hidden shadow-lg w-full min-w-0">
                            {/* Code Header */}
                            <div className="flex items-center justify-between px-4 py-2 bg-[#202024] border-b border-zinc-800 text-xs">
                              <div className="flex items-center gap-2">
                                <span className="font-mono font-medium text-purple-400">
                                  symphonylang
                                </span>
                                {msg.isTemplateFallback && (
                                  <span className="text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20 px-2 py-0.5 rounded">
                                    Template Engine
                                  </span>
                                )}
                              </div>

                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleCopyCode(msg.id, msg.code!)}
                                  className="flex items-center gap-1 px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-700/60 transition-colors"
                                  title="Copy code"
                                >
                                  {copiedCodeId === msg.id ? (
                                    <>
                                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                                      <span className="text-emerald-400">Copied</span>
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="h-3.5 w-3.5" />
                                      <span>Copy</span>
                                    </>
                                  )}
                                </button>

                                <button
                                  onClick={() => handleDownloadSource(msg.code!)}
                                  className="flex items-center gap-1 px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-700/60 transition-colors"
                                  title="Download .sym file"
                                >
                                  <Download className="h-3.5 w-3.5" />
                                  <span>.sym</span>
                                </button>

                                <button
                                  onClick={() => triggerCompilation(msg.id, msg.code!)}
                                  disabled={msg.compilation?.status === 'compiling'}
                                  className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-purple-600 hover:bg-purple-500 text-white font-medium transition-colors disabled:opacity-50"
                                  title="Recompile code"
                                >
                                  {msg.compilation?.status === 'compiling' ? (
                                    <>
                                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                      <span>Compiling</span>
                                    </>
                                  ) : (
                                    <>
                                      <Code2 className="h-3.5 w-3.5" />
                                      <span>Compile</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>

                            {/* Code lines */}
                            <pre className="p-4 text-xs font-mono overflow-x-auto text-zinc-200 leading-relaxed bg-[#141416] w-full min-w-0">
                              <code>{msg.code}</code>
                            </pre>
                          </div>
                        )}

                        {/* Compilation Status & Playback Banner */}
                        {msg.compilation && (
                          <div className="space-y-2">
                            {msg.compilation.status === 'compiling' && (
                              <div className="flex items-center gap-2 p-3 rounded-xl bg-purple-950/20 border border-purple-800/40 text-xs text-purple-300">
                                <RefreshCw className="h-4 w-4 animate-spin text-purple-400" />
                                <span>
                                  Compiling with SymphonyLang (Lexer → Parser → Semantic → IR → Optimizer → MIDI)...
                                </span>
                              </div>
                            )}

                            {msg.compilation.status === 'error' && (
                              <div className="p-3.5 rounded-xl bg-red-950/30 border border-red-800/50 text-xs space-y-2">
                                <div className="flex items-center gap-2 font-medium text-red-300">
                                  <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
                                  <span>Compilation Failed</span>
                                </div>
                                {msg.compilation.errors && msg.compilation.errors.length > 0 && (
                                  <div className="space-y-1 font-mono text-red-200 bg-red-950/50 p-2.5 rounded-lg border border-red-900/40">
                                    {msg.compilation.errors.map((err, i) => (
                                      <div key={i}>• {err}</div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}

                            {msg.compilation.status === 'success' && (
                              <div className="space-y-2">
                                <AudioPlayer
                                  messageId={msg.id}
                                  timeline={msg.compilation.timeline}
                                  tracks={msg.compilation.tracks}
                                  totalDurationSec={msg.compilation.totalDurationSec}
                                  bpm={msg.compilation.bpm}
                                  midiUrl={msg.compilation.midiUrl}
                                  activePlayingId={activePlayingId}
                                  setActivePlayingId={setActivePlayingId}
                                />

                                {/* Expandable Compiler Pipeline Diagnostics */}
                                <div className="pt-1 px-1">
                                  <button
                                    onClick={() =>
                                      setExpandedOutputId(
                                        expandedOutputId === msg.id ? null : msg.id
                                      )
                                    }
                                    className="flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
                                  >
                                    {expandedOutputId === msg.id ? (
                                      <>
                                        <ChevronUp className="h-3 w-3" />
                                        <span>Hide compiler pipeline diagnostics</span>
                                      </>
                                    ) : (
                                      <>
                                        <ChevronDown className="h-3 w-3" />
                                        <span>Show compiler pipeline diagnostics</span>
                                      </>
                                    )}
                                  </button>

                                  {expandedOutputId === msg.id && (
                                    <pre className="mt-2 p-3 rounded-xl bg-[#18181b] border border-zinc-800 text-[11px] font-mono text-zinc-300 whitespace-pre-wrap leading-relaxed shadow-inner">
                                      {msg.compilation.output}
                                    </pre>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ----------------- PROMPT COMPOSER ----------------- */}
        <div className="absolute bottom-0 left-0 right-0 p-4 md:p-6 bg-gradient-to-t from-[#212121] via-[#212121]/95 to-transparent z-10 pointer-events-none">
          <div className="max-w-3xl mx-auto pointer-events-auto">
            <div className="flex flex-col rounded-3xl bg-[#2f2f2f] border border-[#3e3e3e] shadow-2xl focus-within:border-zinc-500 transition-all">
              <textarea
                ref={textareaRef}
                value={inputPrompt}
                onChange={handleTextareaChange}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                disabled={isGenerating}
                rows={1}
                placeholder="Describe music to compose (e.g. Create a cheerful piano melody)..."
                className="w-full bg-transparent px-5 pt-4 pb-2 text-sm text-zinc-100 placeholder-zinc-400 focus:outline-none resize-none max-h-44 min-h-[48px]"
              />

              <div className="flex items-center justify-between px-3.5 pb-3 pt-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-zinc-400 hidden sm:inline">
                    Use Shift+Enter for new line
                  </span>
                </div>

                <button
                  onClick={() => handleSend()}
                  disabled={!inputPrompt.trim() || isGenerating}
                  className={`h-8 w-8 rounded-full flex items-center justify-center transition-all ${
                    inputPrompt.trim() && !isGenerating
                      ? 'bg-white text-black hover:bg-zinc-200 shadow'
                      : 'bg-[#424242] text-zinc-500 cursor-not-allowed'
                  }`}
                  title="Send prompt"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </div>

            <p className="text-[11px] text-center text-zinc-500 mt-2">
              SymphonyLang compiles custom code to genuine Type 1 MIDI files.
            </p>
          </div>
        </div>
      </main>

      {/* ----------------- SETTINGS MODAL ----------------- */}
      {showSettingsModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#282828] border border-zinc-700 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <Sliders className="h-4 w-4 text-purple-400" />
                SymphonyLang Engine Settings
              </h3>
              <button
                onClick={() => setShowSettingsModal(false)}
                className="text-zinc-400 hover:text-white p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-zinc-300">
              <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1.5">
                <div className="font-medium text-white flex items-center justify-between">
                  <span>Active Code Generator</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] ${
                      health?.has_llm_key
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                    }`}
                  >
                    {health?.has_llm_key ? 'LLM Provider' : 'Built-in Fallback'}
                  </span>
                </div>
                <p className="text-zinc-400 leading-relaxed">
                  {health?.has_llm_key
                    ? `Generating via ${health.active_provider}.`
                    : 'Currently using the built-in intelligent composition engine. To enable external LLM generation, define OPENAI_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY in your backend .env file.'}
                </p>
              </div>

              <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800 space-y-1.5">
                <div className="font-medium text-white">Supported General MIDI Instruments</div>
                <div className="flex flex-wrap gap-1 mt-1">
                  {health?.supported_instruments?.map((inst) => (
                    <span
                      key={inst}
                      className="bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded text-[10px] border border-zinc-700"
                    >
                      {inst}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <button
              onClick={() => setShowSettingsModal(false)}
              className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-medium transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      )}

      {/* ----------------- SYNTAX GUIDE MODAL ----------------- */}
      {showDocsModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#282828] border border-zinc-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-zinc-700 pb-3">
              <h3 className="font-semibold text-white flex items-center gap-2 text-sm">
                <HelpCircle className="h-4 w-4 text-purple-400" />
                SymphonyLang Language Guide
              </h3>
              <button
                onClick={() => setShowDocsModal(false)}
                className="text-zinc-400 hover:text-white p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 text-xs text-zinc-300 pr-1">
              <div className="space-y-1">
                <div className="font-medium text-white">Musical Primitives</div>
                <pre className="p-2.5 rounded-lg bg-zinc-900 text-purple-300 font-mono text-[11px] leading-relaxed">
{`TEMPO 120;
INSTRUMENT Piano;
PLAY C4 quarter;
PLAY G4 half;
REST eighth;`}
                </pre>
              </div>

              <div className="space-y-1">
                <div className="font-medium text-white">Loops & Functions</div>
                <pre className="p-2.5 rounded-lg bg-zinc-900 text-purple-300 font-mono text-[11px] leading-relaxed">
{`FUNCTION Theme(x)
    PLAY C4 eighth;
    PLAY E4 eighth;
ENDFUNCTION

CALL Theme(1);

FOR i = 1 TO 4
    PLAY G4 eighth;
ENDFOR`}
                </pre>
              </div>

              <div className="space-y-1">
                <div className="font-medium text-white">Parallel Multi-Track Audio</div>
                <pre className="p-2.5 rounded-lg bg-zinc-900 text-purple-300 font-mono text-[11px] leading-relaxed">
{`PARALLEL
    TRACK ViolinTrack
        INSTRUMENT Violin;
        PLAY C4 whole;
    ENDTRACK
    TRACK CelloTrack
        INSTRUMENT Cello;
        PLAY C3 whole;
    ENDTRACK
ENDPARALLEL`}
                </pre>
              </div>
            </div>

            <button
              onClick={() => setShowDocsModal(false)}
              className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-medium transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
