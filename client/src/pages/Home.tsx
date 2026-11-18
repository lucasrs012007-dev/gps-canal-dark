import { useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronRight,
  CircleDot,
  Clock3,
  Compass,
  Flag,
  Leaf,
  LockKeyhole,
  Mic2,
  PencilLine,
  Play,
  Radio,
  RotateCcw,
  Sparkles,
  TimerReset,
  WandSparkles,
  Zap,
} from "lucide-react";

type Tone = "green" | "yellow";

type Phase = {
  id: number;
  eyebrow: string;
  name: string;
  short: string;
  icon: typeof PencilLine;
  keywords: string[];
};

type Analysis = {
  phaseIndex: number;
  location: string;
  detail: string;
  tone: Tone;
  verdict: string;
  verdictDetail: string;
  microStep: string;
  shortcut: string;
  updatedAt: string;
};

type HistoryEntry = {
  text: string;
  createdAt: string;
};

type PersistedState = {
  status?: string;
  analysis?: Analysis;
  history?: HistoryEntry[];
};

const STORAGE_KEY = "gpsdiario.state.v1";

const phases: Phase[] = [
  {
    id: 1,
    eyebrow: "01",
    name: "Nicho e Roteiro",
    short: "clareza",
    icon: PencilLine,
    keywords: [
      "nicho",
      "roteiro",
      "premissa",
      "tema",
      "publico",
      "público",
      "ideia",
      "gancho",
      "titulo",
      "título",
      "pesquisa",
    ],
  },
  {
    id: 2,
    eyebrow: "02",
    name: "Mídia 60/40",
    short: "matéria-prima",
    icon: Radio,
    keywords: [
      "midia",
      "mídia",
      "b-roll",
      "visual",
      "imagem",
      "imagens",
      "video",
      "vídeo",
      "stock",
      "60/40",
      "captacao",
      "captação",
    ],
  },
  {
    id: 3,
    eyebrow: "03",
    name: "Voz Local",
    short: "presença",
    icon: Mic2,
    keywords: [
      "voz",
      "locucao",
      "locução",
      "narracao",
      "narração",
      "audio",
      "áudio",
      "dublagem",
      "voice",
      "tts",
    ],
  },
  {
    id: 4,
    eyebrow: "04",
    name: "Edição Automática",
    short: "ritmo",
    icon: WandSparkles,
    keywords: [
      "edicao",
      "edição",
      "python",
      "ffmpeg",
      "render",
      "legenda",
      "corte",
      "script",
      "automacao",
      "automação",
      "exportar",
    ],
  },
];

const INITIAL_STATUS =
  "Dia 1: vou definir o nicho do canal e escrever a premissa do roteiro.";

const INITIAL_ANALYSIS: Analysis = {
  phaseIndex: 0,
  location: "Definir o nicho + escrever a premissa",
  detail: "Primeira micro-missão do Dia 1 · ponto de partida",
  tone: "yellow",
  verdict: "Continue só mais 10 minutos para fechar este ponto.",
  verdictDetail: "Uma frase basta para tirar a ideia da cabeça e colocar na linha.",
  microStep: "Escreva uma premissa de uma frase: quem vive o quê e por que isso importa.",
  shortcut: "Escolha uma dor específica do público; clareza vence originalidade agora.",
  updatedAt: "agora",
};

function readPersistedState(): PersistedState | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PersistedState) : null;
  } catch {
    return null;
  }
}

function writePersistedState(
  status: string,
  analysis: Analysis,
  history: HistoryEntry[],
) {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ status, analysis, history }),
    );
  } catch {
    // O painel segue funcionando mesmo se o navegador bloquear o localStorage.
  }
}

function normalize(value: string) {
  return value.toLocaleLowerCase("pt-BR");
}

function detectPhase(text: string) {
  const normalized = normalize(text);
  const scores = phases.map((phase) =>
    phase.keywords.reduce(
      (score, keyword) => score + (normalized.includes(keyword) ? 1 : 0),
      0,
    ),
  );
  const strongest = Math.max(...scores);
  return strongest > 0 ? scores.indexOf(strongest) : 0;
}

function analyzeStatus(text: string): Analysis {
  const cleanText = text.trim() || INITIAL_STATUS;
  const normalized = normalize(cleanText);
  const phaseIndex = detectPhase(cleanText);
  const phase = phases[phaseIndex];
  const doneSignal = /(conclu|finaliz|terminei|termine|feito|feita|pronto|pronta|entreg|publiquei|avancei|resolvi|fechei)/.test(
    normalized,
  );
  const timeSignal = /\b(1[5-9]|20)\s*(min|minuto|minutos)\b|quinze minutos|vinte minutos/.test(
    normalized,
  );
  const blockSignal = /(trav|dúvid|duvid|erro|não sei|nao sei|parad|falt|confus|cansad)/.test(
    normalized,
  );
  const green = doneSignal || timeSignal;
  const phaseDetails = [
    {
      location: "Definir o nicho + escrever a premissa",
      detail: "Dia 1 · clareza antes de qualquer ferramenta",
      microStep:
        "Escreva uma premissa de uma frase: quem vive o quê e por que isso importa.",
      shortcut:
        "Escolha uma dor específica do público; clareza vence originalidade agora.",
    },
    {
      location: "Separar a mídia na proporção 60/40",
      detail: "Captação · apoio visual sem virar pesquisa infinita",
      microStep:
        "Separe três referências visuais que sustentem o primeiro roteiro.",
      shortcut:
        "Use uma única pasta com nomes 01, 02 e 03; não abra uma nova busca.",
    },
    {
      location: "Gerar e revisar a voz local",
      detail: "Áudio · presença humana antes do acabamento",
      microStep:
        "Gere uma amostra de 20 segundos da primeira fala e escute uma vez.",
      shortcut:
        "Fixe uma voz e um ritmo para o piloto; variedade fica para depois.",
    },
    {
      location: "Rodar a edição automática e conferir o render",
      detail: "Python/FFmpeg · transformar peças em um primeiro corte",
      microStep:
        "Rode o script com um único clipe e verifique se o arquivo final abre.",
      shortcut:
        "Teste o menor arquivo possível; o objetivo é provar o fluxo, não polir.",
    },
  ][phaseIndex];

  return {
    phaseIndex,
    location: phaseDetails.location,
    detail: phaseDetails.detail,
    tone: green ? "green" : "yellow",
    verdict: green
      ? "POR HOJE ESTÁ ÓTIMO! Feche tudo e vá descansar"
      : "Continue só mais 10 minutos para fechar este ponto.",
    verdictDetail: green
      ? "Você já colocou um marco concreto na linha. Constância também é saber parar."
      : blockSignal
        ? "Não abra outra frente: retire só a trava que está na sua frente."
        : "Falta só um gesto curto para transformar intenção em avanço visível.",
    microStep: phaseDetails.microStep,
    shortcut: phaseDetails.shortcut,
    updatedAt: "agora",
  };
}

function formatCount(value: number) {
  if (value === 0) return "nenhum registro anterior";
  if (value === 1) return "1 registro salvo";
  return `${value} registros salvos`;
}

export default function Home() {
  const persisted = useMemo(() => readPersistedState(), []);
  const [statusText, setStatusText] = useState(persisted?.status ?? INITIAL_STATUS);
  const [analysis, setAnalysis] = useState(
    persisted?.analysis ?? INITIAL_ANALYSIS,
  );
  const [history, setHistory] = useState<HistoryEntry[]>(persisted?.history ?? []);
  const [isFocused, setIsFocused] = useState(false);

  const currentPhase = phases[analysis.phaseIndex];
  const progress = Math.round(((analysis.phaseIndex + 0.35) / phases.length) * 100);
  const Icon = currentPhase.icon;
  const nowLabel = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());

  function handleUpdate() {
    const nextAnalysis = analyzeStatus(statusText);
    const nextHistory = [
      { text: statusText.trim() || INITIAL_STATUS, createdAt: nowLabel },
      ...history,
    ].slice(0, 12);
    setAnalysis(nextAnalysis);
    setHistory(nextHistory);
    writePersistedState(statusText.trim() || INITIAL_STATUS, nextAnalysis, nextHistory);
  }

  function handleReset() {
    setStatusText(INITIAL_STATUS);
    setAnalysis(INITIAL_ANALYSIS);
    setHistory([]);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // no-op
    }
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[#F5F2EB] text-[#18343A]">
      <div className="pointer-events-none fixed inset-0 opacity-30 [background-image:linear-gradient(rgba(24,52,58,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(24,52,58,0.04)_1px,transparent_1px)] [background-size:36px_36px]" />
      <div className="relative mx-auto max-w-[1440px] px-5 py-5 sm:px-8 lg:px-12 lg:py-8">
        <header className="flex flex-col gap-5 border-b border-[#18343A]/15 pb-7 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="mt-1 flex size-11 shrink-0 items-center justify-center rounded-full bg-[#18343A] text-[#F8C76C] shadow-[0_8px_20px_rgba(24,52,58,0.16)]">
              <Compass className="size-5" strokeWidth={1.8} />
            </div>
            <div>
              <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.25em] text-[#6C7771]">
                <span>GPS // execução diária</span>
                <span className="size-1 rounded-full bg-[#E6A44A]" />
                <span>painel 01</span>
              </div>
              <h1 className="max-w-2xl font-serif text-3xl leading-[0.98] tracking-[-0.045em] text-[#18343A] sm:text-5xl">
                Uma linha reta para sair do pensar e entrar no fazer.
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-[#61716D]">
                Seu canal dark em quatro movimentos. O painel lê onde você parou,
                segura o excesso e libera apenas o próximo passo.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 self-start rounded-full border border-[#18343A]/15 bg-[#F8F6F0]/75 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#61716D] backdrop-blur-sm">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-[#4A9B86] opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-[#4A9B86]" />
            </span>
            <span>salvo neste navegador</span>
            <span className="text-[#18343A]/30">/</span>
            <span>Dia 01</span>
          </div>
        </header>

        <section className="border-b border-[#18343A]/15 py-7" aria-label="Progresso da esteira">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#C27C2B]">
                A esteira
              </p>
              <p className="mt-1 text-sm text-[#61716D]">
                Fase atual <span className="font-semibold text-[#18343A]">0{currentPhase.id} de 04</span>
                <span className="mx-2 text-[#18343A]/30">·</span>
                {currentPhase.short}
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-[#61716D]">
              <span className="font-serif text-2xl tracking-[-0.04em] text-[#18343A]">{progress}%</span>
              <span>da linha em movimento</span>
            </div>
          </div>
          <div className="relative h-1.5 rounded-full bg-[#18343A]/10">
            <div
              className="absolute left-0 top-0 h-1.5 rounded-full bg-[#4A9B86] transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-5 grid grid-cols-2 gap-x-3 gap-y-4 lg:grid-cols-4 lg:gap-0">
            {phases.map((phase, index) => {
              const PhaseIcon = phase.icon;
              const isCurrent = index === analysis.phaseIndex;
              const isDone = index < analysis.phaseIndex;
              return (
                <div className="relative flex items-start gap-3 lg:pr-5" key={phase.id}>
                  {index < phases.length - 1 ? (
                    <div className="absolute left-3 top-3 hidden h-px w-[calc(100%-1.25rem)] bg-[#18343A]/10 lg:block" />
                  ) : null}
                  <div
                    className={`relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border text-[10px] transition-colors ${
                      isCurrent
                        ? "border-[#18343A] bg-[#18343A] text-[#F8C76C]"
                        : isDone
                          ? "border-[#4A9B86] bg-[#4A9B86] text-[#F8F6F0]"
                          : "border-[#18343A]/20 bg-[#F5F2EB] text-[#8A9690]"
                    }`}
                  >
                    {isDone ? <Check className="size-3.5" /> : <PhaseIcon className="size-3.5" strokeWidth={1.8} />}
                  </div>
                  <div className="pt-0.5">
                    <p className={`text-[10px] font-bold uppercase tracking-[0.13em] ${isCurrent ? "text-[#18343A]" : "text-[#8A9690]"}`}>
                      {phase.eyebrow} / {isCurrent ? "agora" : phase.short}
                    </p>
                    <p className={`mt-1 text-sm ${isCurrent ? "font-semibold text-[#18343A]" : "text-[#61716D]"}`}>
                      {phase.name}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="grid gap-7 py-8 lg:grid-cols-[minmax(260px,0.72fr)_minmax(0,1.28fr)] lg:gap-12 lg:py-10">
          <div className="flex flex-col justify-between">
            <div>
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#C27C2B]">
                    Registro de bordo
                  </p>
                  <h2 className="mt-2 font-serif text-3xl tracking-[-0.04em] text-[#18343A]">
                    O que está acontecendo?
                  </h2>
                </div>
                <div className="hidden rounded-full border border-[#18343A]/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A9690] sm:block">
                  {formatCount(history.length)}
                </div>
              </div>
              <p className="mb-4 max-w-sm text-sm leading-6 text-[#61716D]">
                Escreva do seu jeito. Pode ser avanço, dúvida ou trava. O painel
                encontra o ponto e corta o ruído.
              </p>
              <div className={`relative rounded-[1.25rem] border bg-[#FBFAF6] p-1.5 shadow-[0_14px_40px_rgba(24,52,58,0.05)] transition-all ${isFocused ? "border-[#4A9B86] ring-4 ring-[#4A9B86]/10" : "border-[#18343A]/15"}`}>
                <textarea
                  value={statusText}
                  onChange={(event) => setStatusText(event.target.value)}
                  onFocus={() => setIsFocused(true)}
                  onBlur={() => setIsFocused(false)}
                  className="min-h-[168px] w-full resize-none rounded-[0.9rem] border-0 bg-transparent px-4 py-4 text-base leading-7 text-[#18343A] outline-none placeholder:text-[#9AA49D]"
                  placeholder="Ex.: travei na escolha das referências visuais..."
                  aria-label="Seu status de execução"
                />
                <div className="flex items-center justify-between border-t border-[#18343A]/10 px-3 py-3">
                  <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8A9690]">
                    <LockKeyhole className="size-3.5" />
                    histórico local
                  </span>
                  <button
                    type="button"
                    onClick={handleUpdate}
                    className="group inline-flex items-center gap-2 rounded-full bg-[#18343A] px-4 py-2.5 text-xs font-semibold text-[#F8F6F0] shadow-[0_5px_0_#0d252a] transition-all hover:-translate-y-0.5 hover:bg-[#244A50] hover:shadow-[0_7px_0_#0d252a] active:translate-y-0 active:shadow-[0_3px_0_#0d252a]"
                  >
                    Atualizar meu status
                    <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                  </button>
                </div>
              </div>
            </div>
            <div className="mt-6 flex items-center justify-between gap-3 border-t border-[#18343A]/10 pt-4">
              <p className="flex items-center gap-2 text-xs text-[#61716D]">
                <Clock3 className="size-3.5 text-[#C27C2B]" />
                última leitura: {analysis.updatedAt === "agora" ? "agora" : analysis.updatedAt}
              </p>
              <button
                type="button"
                onClick={handleReset}
                className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[#8A9690] transition-colors hover:text-[#18343A]"
              >
                <RotateCcw className="size-3" />
                reiniciar dia 01
              </button>
            </div>
          </div>

          <div aria-live="polite" className="grid gap-4">
            <article className="relative overflow-hidden rounded-[1.5rem] border border-[#18343A] bg-[#18343A] p-6 text-[#F8F6F0] shadow-[0_18px_42px_rgba(24,52,58,0.15)] sm:p-8">
              <div className="absolute -right-8 -top-10 size-40 rounded-full border border-[#F8C76C]/20" />
              <div className="absolute -right-1 -top-3 size-24 rounded-full border border-[#F8C76C]/10" />
              <div className="relative flex flex-col gap-7 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <div className="mb-5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-[#F8C76C]">
                    <CircleDot className="size-3.5" />
                    cartão 01 / linha reta
                  </div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-[0.13em] text-[#AFC1BA]">
                    Onde você está
                  </p>
                  <h3 className="max-w-xl font-serif text-3xl leading-[1.03] tracking-[-0.04em] text-[#F8F6F0] sm:text-4xl">
                    {analysis.location}
                  </h3>
                  <p className="mt-4 flex items-center gap-2 text-sm text-[#AFC1BA]">
                    <Icon className="size-4 text-[#F8C76C]" strokeWidth={1.7} />
                    {analysis.detail}
                  </p>
                </div>
                <div className="shrink-0 self-start rounded-full border border-[#F8F6F0]/15 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.16em] text-[#D6E2DC] sm:self-end">
                  {currentPhase.eyebrow} / em andamento
                </div>
              </div>
            </article>

            <div className="grid gap-4 md:grid-cols-2">
              <article className={`rounded-[1.5rem] border p-6 shadow-[0_12px_30px_rgba(24,52,58,0.04)] ${analysis.tone === "green" ? "border-[#4A9B86]/35 bg-[#E7F1E8]" : "border-[#D99A45]/35 bg-[#FFF2D7]"}`}>
                <div className={`mb-5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] ${analysis.tone === "green" ? "text-[#26745F]" : "text-[#9A631F]"}`}>
                  {analysis.tone === "green" ? <Leaf className="size-3.5" /> : <TimerReset className="size-3.5" />}
                  cartão 02 / freio de hoje
                </div>
                <p className="mb-3 text-xs font-medium uppercase tracking-[0.13em] text-[#61716D]">
                  Veredito
                </p>
                <h3 className="font-serif text-2xl leading-[1.05] tracking-[-0.035em] text-[#18343A]">
                  {analysis.verdict}
                </h3>
                <p className="mt-4 text-sm leading-6 text-[#61716D]">{analysis.verdictDetail}</p>
                <div className="mt-6 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.13em] text-[#8A9690]">
                  <Zap className="size-3.5 text-[#C27C2B]" />
                  limite gentil, avanço real
                </div>
              </article>

              <article className="rounded-[1.5rem] border border-[#18343A]/15 bg-[#FBFAF6] p-6 shadow-[0_12px_30px_rgba(24,52,58,0.04)]">
                <div className="mb-5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.2em] text-[#C27C2B]">
                  <Flag className="size-3.5" />
                  cartão 03 / como prosseguir
                </div>
                <p className="mb-3 text-xs font-medium uppercase tracking-[0.13em] text-[#61716D]">
                  Um micro-passo
                </p>
                <h3 className="text-base font-semibold leading-6 text-[#18343A]">
                  {analysis.microStep}
                </h3>
                <div className="mt-5 border-t border-[#18343A]/10 pt-4">
                  <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.13em] text-[#8A9690]">
                    Para cortar caminho
                  </p>
                  <p className="text-sm leading-6 text-[#61716D]">{analysis.shortcut}</p>
                </div>
                <div className="mt-6 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.13em] text-[#4A9B86]">
                  <Play className="size-3.5 fill-current" />
                  só este movimento
                </div>
              </article>
            </div>
          </div>
        </section>

        <footer className="flex flex-col gap-3 border-t border-[#18343A]/15 py-5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A9690] sm:flex-row sm:items-center sm:justify-between">
          <span>Canal Dark / esteira 04 fases / foco sem sobrecarga</span>
          <span className="flex items-center gap-2">
            {formatCount(history.length)}
            <ChevronRight className="size-3" />
            um passo por vez
          </span>
        </footer>
      </div>
    </main>
  );
}
