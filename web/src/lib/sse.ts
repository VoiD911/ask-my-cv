/**
 * Analyseur SSE incrémental, indépendant du transport.
 *
 * `fetch` + `ReadableStream` livre le corps par morceaux arbitraires : un
 * événement peut être coupé entre deux morceaux, plusieurs événements
 * peuvent tenir dans un seul morceau, et les fins de ligne peuvent être
 * `\n` ou `\r\n` (potentiellement coupées elles aussi, un `\r` isolé en fin
 * de morceau). `createSseParser` accumule un tampon et n'émet un événement
 * `{event, data}` que lorsqu'un bloc complet (terminé par une ligne vide) a
 * été reçu.
 *
 * Champ `data:` manquant sur un bloc, ou ligne dans le bloc qui ne
 * correspond à aucun champ SSE reconnu (`event:`, `data:`, `id:`, `retry:`,
 * commentaire `:...`) : le bloc/la ligne est ignoré(e) et le compteur
 * `errorCount` est incrémenté. Ce module ne fait aucune hypothèse sur le
 * contenu de `data` (JSON ou non) : cette décision appartient à l'appelant.
 */

export interface SseMessage {
  readonly event: string;
  readonly data: string;
}

export interface SseParser {
  /** Ajoute un morceau de texte reçu du flux. Peut émettre 0..N événements. */
  push(chunk: string): void;
  /** Nombre de lignes ou blocs invalides rencontrés depuis la création. */
  readonly errorCount: number;
}

const DEFAULT_EVENT_NAME = "message";

const KNOWN_FIELD_PREFIXES = ["event:", "data:", "id:", "retry:"] as const;

function isRecognizedLine(line: string): boolean {
  if (line.trim() === "") return true; // ligne vide interne à un bloc (ne devrait pas arriver)
  if (line.startsWith(":")) return true; // commentaire SSE
  return KNOWN_FIELD_PREFIXES.some((prefix) => line.startsWith(prefix));
}

function stripFieldValue(line: string, prefixLength: number): string {
  const rest = line.slice(prefixLength);
  // La spec SSE ignore un unique espace après les deux-points.
  return rest.startsWith(" ") ? rest.slice(1) : rest;
}

export function createSseParser(onEvent: (message: SseMessage) => void): SseParser {
  let buffer = "";
  let errorCount = 0;

  function processBlock(block: string): void {
    if (block.length === 0) return;

    let eventName = DEFAULT_EVENT_NAME;
    const dataLines: string[] = [];

    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = stripFieldValue(line, "event:".length);
      } else if (line.startsWith("data:")) {
        dataLines.push(stripFieldValue(line, "data:".length));
      } else if (!isRecognizedLine(line)) {
        errorCount += 1;
      }
      // id:/retry:/commentaires : reconnus mais non exploités ici.
    }

    if (dataLines.length === 0) {
      errorCount += 1;
      return;
    }

    onEvent({ event: eventName, data: dataLines.join("\n") });
  }

  function push(chunk: string): void {
    buffer += chunk;

    // Un `\r` en toute fin de tampon peut être la moitié d'un `\r\n` scindé
    // entre deux morceaux : on le retient tant qu'on ne sait pas ce qui suit.
    let pendingCr = "";
    if (buffer.endsWith("\r")) {
      pendingCr = "\r";
      buffer = buffer.slice(0, -1);
    }

    buffer = buffer.replace(/\r\n/g, "\n");

    const blocks = buffer.split("\n\n");
    buffer = (blocks.pop() ?? "") + pendingCr;

    for (const block of blocks) {
      processBlock(block);
    }
  }

  return {
    push,
    get errorCount() {
      return errorCount;
    },
  };
}
