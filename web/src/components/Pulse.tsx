/**
 * Impulsion le long d'une piste du circuit.
 *
 * - `travel` : une tête lumineuse suivie d'une traînée parcourt la piste en
 *   boucle (animation CSS de `stroke-dashoffset` sur une longueur normalisée
 *   par `pathLength`, donc indépendante de la géométrie) ;
 * - `halt` : l'impulsion s'est arrêtée au bout de la piste — point rouge fixe.
 *
 * Avec `reducedMotion`, `travel` ne dessine rien : la piste et le nœud
 * portent seuls l'état (le point d'arrêt, statique, reste affiché).
 */
export type PulseMode = "travel" | "halt";

type PulseProps = {
  /** Chemin SVG de la piste, de l'étape terminée vers l'étape active. */
  d: string;
  mode: PulseMode;
  /** Extrémité de la piste (nœud bloqué), requise pour `halt`. */
  end?: { x: number; y: number };
  reducedMotion?: boolean;
};

export function Pulse({ d, mode, end, reducedMotion = false }: PulseProps) {
  if (mode === "halt") {
    if (!end) return null;
    return (
      <g className="pulse-halt" data-testid="pulse-halt">
        <circle cx={end.x} cy={end.y} r={9} className="pulse-halt__ring" />
        <circle cx={end.x} cy={end.y} r={4} className="pulse-halt__dot" />
      </g>
    );
  }

  if (reducedMotion) return null;

  return (
    <g className="pulse" data-testid="pulse" aria-hidden="true">
      <path d={d} pathLength={100} className="pulse__tail" />
      <path d={d} pathLength={100} className="pulse__head" />
    </g>
  );
}
