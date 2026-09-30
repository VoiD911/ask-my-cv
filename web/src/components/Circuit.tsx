"use client";

import "@xyflow/react/dist/base.css";

import {
  Background,
  BackgroundVariant,
  Handle,
  Position,
  ReactFlow,
  useReactFlow,
  useStore,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { useEffect, useMemo } from "react";

import { translator } from "@/i18n/translator";
import {
  describe,
  formatNumber,
  formatUsd,
  stageLabel,
  statusLabel,
  type RunState,
  type StageState,
} from "@/lib/pipeline";

import { Pulse } from "./Pulse";
import { StageNode, Terminal, formatDuration, type TerminalState } from "./StageNode";
import { useReducedMotion } from "./useReducedMotion";

/* ------------------------------------------------------------------ */
/* Modèle : état du run → pistes et connecteurs (pur, testé à part)    */
/* ------------------------------------------------------------------ */

export const IN = "__in";
export const OUT = "__out";

/** État d'une piste entre deux éléments du circuit. */
export type TraceState = "idle" | "live" | "lit" | "halted";

export type Trace = { from: string; to: string; state: TraceState };

const PASSED: ReadonlySet<StageState["status"]> = new Set(["ok", "fallback"]);
const STOPPED: ReadonlySet<StageState["status"]> = new Set(["blocked", "error"]);

function isRunning(state: RunState): boolean {
  return (
    state.startedAt !== null ||
    state.done !== null ||
    Object.values(state.stages).some((s) => s.status !== "idle")
  );
}

function traceInto(state: RunState, from: string, to: string): TraceState {
  if (to === OUT) {
    const last = state.stages[from];
    if (state.done) return state.blockedAt ? "idle" : "lit";
    return last && PASSED.has(last.status) ? "live" : "idle";
  }
  const status = state.stages[to]?.status ?? "idle";
  if (status === "active") return "live";
  if (STOPPED.has(status)) return "halted";
  if (PASSED.has(status)) return "lit";
  return "idle";
}

/** Pistes du circuit : entrée → étapes (dans l'ordre d'affichage) → sortie. */
export function traces(state: RunState): Trace[] {
  const chain = [IN, ...state.order, OUT];
  const out: Trace[] = [];
  for (let i = 1; i < chain.length; i += 1) {
    const from = chain[i - 1] as string;
    const to = chain[i] as string;
    out.push({ from, to, state: traceInto(state, from, to) });
  }
  return out;
}

export function terminalStates(state: RunState): { in: TerminalState; out: TerminalState } {
  const running = isRunning(state);
  let out: TerminalState = "standby";
  if (state.done) out = state.blockedAt ? "blocked" : "ok";
  else if (traces(state).at(-1)?.state === "live") out = "live";
  return { in: running ? "ok" : "standby", out };
}

/** Libellé de l'image : l'état de chaque étape, lisible par un lecteur d'écran. */
export function circuitLabel(state: RunState): string {
  const { locale } = state;
  const parts = state.order.map((name) => {
    const status = state.stages[name]?.status ?? "idle";
    return `${stageLabel(name, locale)} ${statusLabel(status, locale)}`;
  });
  return translator(locale)("circuit.label", { count: state.order.length, parts: parts.join(", ") });
}

/* ------------------------------------------------------------------ */
/* Disposition en serpentin : rangées de 4, sens alterné               */
/* ------------------------------------------------------------------ */

const PER_ROW = 4;
const NODE_W = 184;
const NODE_H = 116;
const TERM_W = 112;
const TERM_H = 36;
const GAP_X = 48;
const GAP_Y = 72;
const LEAD = 44; // longueur de piste entre un connecteur et sa puce
const TURN = 36; // débord des pistes qui changent de rangée
const CHAMFER = 10;

type Slot = { x: number; y: number; row: number; forward: boolean };

function slot(i: number): Slot {
  const row = Math.floor(i / PER_ROW);
  const forward = row % 2 === 0;
  const col = forward ? i % PER_ROW : PER_ROW - 1 - (i % PER_ROW);
  return { x: TERM_W + LEAD + col * (NODE_W + GAP_X), y: row * (NODE_H + GAP_Y), row, forward };
}

type StageData = { kind: "stage"; name: string; index: number; stage: StageState; tokens: number };
type TermData = { kind: "in" | "out"; state: TerminalState };
type Localized = { locale: RunState["locale"] };
type NodeData = (StageData | TermData) & Localized & { inSide: Position; outSide: Position };
type TraceData = { state: TraceState; reducedMotion: boolean };

type CircuitNode = Node<NodeData, "chip"> | Node<Record<string, never>, "bound">;
type CircuitEdge = Edge<TraceData, "trace">;

function layout(state: RunState, reducedMotion: boolean) {
  const nodes: CircuitNode[] = [];
  const termY = (NODE_H - TERM_H) / 2;
  const terms = terminalStates(state);

  nodes.push({
    id: IN,
    type: "chip",
    position: { x: 0, y: termY },
    width: TERM_W,
    height: TERM_H,
    data: { kind: "in", state: terms.in, locale: state.locale, inSide: Position.Left, outSide: Position.Right },
  });

  state.order.forEach((name, index) => {
    const s = slot(index);
    const side = s.forward ? Position.Right : Position.Left;
    const opposite = s.forward ? Position.Left : Position.Right;
    const firstOfRow = index % PER_ROW === 0 && s.row > 0;
    nodes.push({
      id: name,
      type: "chip",
      position: { x: s.x, y: s.y },
      width: NODE_W,
      height: NODE_H,
      data: {
        kind: "stage",
        name,
        index,
        stage: state.stages[name] ?? { status: "idle", attrs: {} },
        tokens: state.tokens,
        locale: state.locale,
        // La première puce d'une rangée reçoit la piste du côté du virage.
        inSide: firstOfRow ? side : opposite,
        outSide: side,
      },
    });
  });

  // La sortie prolonge la dernière rangée dans son sens de parcours.
  const last = slot(Math.max(state.order.length - 1, 0));
  const outX = last.forward ? last.x + NODE_W + LEAD : last.x - LEAD - TERM_W;
  nodes.push({
    id: OUT,
    type: "chip",
    position: { x: outX, y: last.y + termY },
    width: TERM_W,
    height: TERM_H,
    data: {
      kind: "out",
      state: terms.out,
      locale: state.locale,
      inSide: last.forward ? Position.Left : Position.Right,
      outSide: last.forward ? Position.Right : Position.Left,
    },
  });

  const edges: CircuitEdge[] = traces(state).map((t) => ({
    id: `${t.from}->${t.to}`,
    source: t.from,
    target: t.to,
    type: "trace",
    data: { state: t.state, reducedMotion },
  }));

  const minX = Math.min(...nodes.map((n) => n.position.x));
  const maxX = Math.max(...nodes.map((n) => n.position.x + (n.width ?? 0))) + TURN + 4;
  const maxY = Math.max(...nodes.map((n) => n.position.y + (n.height ?? 0)));
  // Borne invisible : `fitView` cadre les nœuds, pas les virages des pistes.
  nodes.push({ id: "__bound", type: "bound", position: { x: maxX, y: 0 }, width: 1, height: 1, data: {} });
  return { nodes, edges, width: maxX - minX, height: maxY };
}

/* ------------------------------------------------------------------ */
/* Rendu React Flow (lecture seule)                                    */
/* ------------------------------------------------------------------ */

type ChipFlowNode = Extract<CircuitNode, { type: "chip" }>;

function ChipNode({ data }: NodeProps<ChipFlowNode>) {
  return (
    <>
      <Handle type="target" position={data.inSide} isConnectable={false} className="handle" />
      {data.kind === "stage" ? (
        <StageNode
          name={data.name}
          index={data.index}
          stage={data.stage}
          liveTokens={data.tokens}
          locale={data.locale}
        />
      ) : (
        <Terminal kind={data.kind} state={data.state} locale={data.locale} />
      )}
      <Handle type="source" position={data.outSide} isConnectable={false} className="handle" />
    </>
  );
}

/** Piste droite, ou virage chanfreiné à 45° quand elle change de rangée. */
export function tracePath(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  side: Position,
): { d: string; vias: Array<{ x: number; y: number }> } {
  if (Math.abs(sy - ty) < 1) return { d: `M ${sx} ${sy} L ${tx} ${ty}`, vias: [] };
  const right = side === Position.Right;
  const x1 = right ? Math.max(sx, tx) + TURN : Math.min(sx, tx) - TURN;
  const c = right ? -CHAMFER : CHAMFER;
  const d = [
    `M ${sx} ${sy}`,
    `L ${x1 + c} ${sy}`,
    `L ${x1} ${sy + CHAMFER}`,
    `L ${x1} ${ty - CHAMFER}`,
    `L ${x1 + c} ${ty}`,
    `L ${tx} ${ty}`,
  ].join(" ");
  return { d, vias: [{ x: x1, y: (sy + ty) / 2 }] };
}

function TraceEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, data }: EdgeProps<CircuitEdge>) {
  const state = data?.state ?? "idle";
  const { d, vias } = tracePath(sourceX, sourceY, targetX, targetY, sourcePosition);
  return (
    <g className="trace" data-state={state}>
      <path d={d} className="trace__line" />
      {vias.map((v) => (
        <circle key={`${v.x},${v.y}`} cx={v.x} cy={v.y} r={4} className="trace__via" />
      ))}
      {state === "live" && <Pulse d={d} mode="travel" reducedMotion={data?.reducedMotion} />}
      {state === "halted" && <Pulse d={d} mode="halt" end={{ x: targetX, y: targetY }} />}
    </g>
  );
}

const nodeTypes = { chip: ChipNode, bound: () => null };
const edgeTypes = { trace: TraceEdge };

/** Recadre le circuit quand la zone change de taille (rotation, redimensionnement). */
function AutoFit({ count }: { count: number }) {
  const { fitView } = useReactFlow();
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  useEffect(() => {
    if (width > 0 && height > 0) void fitView({ padding: 0.04 });
  }, [width, height, count, fitView]);
  return null;
}

function Board({ state, reducedMotion }: { state: RunState; reducedMotion: boolean }) {
  const { nodes, edges, width, height } = useMemo(
    () => layout(state, reducedMotion),
    [state, reducedMotion],
  );
  return (
    <div className="board" style={{ aspectRatio: `${width + 48} / ${height + 48}` }}>
      <ReactFlow<CircuitNode, CircuitEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.04 }}
        minZoom={0.2}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        panOnDrag={false}
        panOnScroll={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} className="board__grid" />
        <AutoFit count={nodes.length} />
      </ReactFlow>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Disposition mobile : colonne de puces reliées                       */
/* ------------------------------------------------------------------ */

const LINK_H = 28;
const LINK_D = `M 8 0 L 8 ${LINK_H}`;

function Link({ trace, reducedMotion }: { trace: Trace; reducedMotion: boolean }) {
  return (
    <svg className="link" width={16} height={LINK_H} viewBox={`0 0 16 ${LINK_H}`}>
      <g className="trace" data-state={trace.state}>
        <path d={LINK_D} className="trace__line" />
        {trace.state === "live" && <Pulse d={LINK_D} mode="travel" reducedMotion={reducedMotion} />}
        {trace.state === "halted" && <Pulse d={LINK_D} mode="halt" end={{ x: 8, y: LINK_H }} />}
      </g>
    </svg>
  );
}

function Column({ state, reducedMotion }: { state: RunState; reducedMotion: boolean }) {
  const links = traces(state);
  const terms = terminalStates(state);
  return (
    <ol className="column" data-testid="circuit-column">
      <li>
        <Terminal kind="in" state={terms.in} locale={state.locale} />
      </li>
      {state.order.map((name, index) => (
        <li key={name}>
          {links[index] && <Link trace={links[index]} reducedMotion={reducedMotion} />}
          <StageNode
            name={name}
            index={index}
            stage={state.stages[name] ?? { status: "idle", attrs: {} }}
            liveTokens={state.tokens}
            locale={state.locale}
          />
        </li>
      ))}
      <li>
        {links.at(-1) && <Link trace={links.at(-1) as Trace} reducedMotion={reducedMotion} />}
        <Terminal kind="out" state={terms.out} locale={state.locale} />
      </li>
    </ol>
  );
}

/* ------------------------------------------------------------------ */
/* Composant public                                                    */
/* ------------------------------------------------------------------ */

function metrics(state: RunState): string {
  const { locale } = state;
  const t = translator(locale);
  if (state.done) {
    const d = state.done;
    return t("circuit.metricsDone", {
      duration: formatDuration(d.latency_ms, locale),
      tokens: formatNumber(d.tokens_out, locale),
      cost: formatUsd(d.cost_usd, locale, { max: 4 }),
    });
  }
  if (state.blockedAt) return t("circuit.halted");
  if (isRunning(state)) {
    return state.tokens > 0
      ? t("circuit.runningTokens", { tokens: formatNumber(state.tokens, locale) })
      : t("circuit.running");
  }
  return t("circuit.idle");
}

type CircuitProps = { state: RunState };

/**
 * Le pipeline dessiné comme un circuit imprimé : chaque étape est une puce,
 * une impulsion suit la piste de la dernière étape terminée vers l'étape en
 * cours, et s'arrête en rouge sur l'étape qui bloque. Purement présentationnel.
 */
export function Circuit({ state }: CircuitProps) {
  const reducedMotion = useReducedMotion();
  return (
    <section className="circuit" aria-labelledby="circuit-title">
      <header className="circuit__bar">
        <h2 id="circuit-title" className="circuit__title">
          {translator(state.locale)("circuit.title")}
        </h2>
        <span className="circuit__metrics">{metrics(state)}</span>
      </header>
      <div role="img" aria-label={circuitLabel(state)} className="circuit__figure">
        <div className="circuit__board">
          <Board state={state} reducedMotion={reducedMotion} />
        </div>
        <div className="circuit__column">
          <Column state={state} reducedMotion={reducedMotion} />
        </div>
      </div>
      <p className="circuit__log" aria-live="polite" aria-atomic="true">
        {describe(state)}
      </p>
    </section>
  );
}
