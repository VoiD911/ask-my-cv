'use strict';

/**
 * Lecture du flux SSE de `POST /ask`, partagée par les suites promptfoo.
 *
 * Le flux est une suite de blocs `event: <type>\ndata: <json>\n\n` (voir
 * src/ask_my_cv/events.py). On en extrait un résumé stable sur lequel les
 * assertions travaillent (`JSON.parse(output)`) :
 *   answer   texte de l'événement `answer` (émis après le garde-fou de sortie) ou null
 *   override `done.answer_override` ou null
 *   blocked  nom de la première étape terminée en statut `blocked` ou null
 *   sources  `done.sources` ([] si absent)
 *   done     true si l'événement `done` a été reçu
 */

function parseEvents(text) {
  const events = [];
  for (const block of String(text ?? '').replace(/\r\n/g, '\n').split('\n\n')) {
    let name = null;
    const data = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) name = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
    }
    if (name === null || data.length === 0) continue;
    try {
      events.push({ name, data: JSON.parse(data.join('\n')) });
    } catch {
      // bloc illisible : ignoré (le résumé le reflétera par un champ nul)
    }
  }
  return events;
}

function summarize(text) {
  const summary = { answer: null, override: null, blocked: null, sources: [], done: false };
  for (const { name, data } of parseEvents(text)) {
    if (name === 'answer' && summary.answer === null && typeof data.text === 'string') {
      summary.answer = data.text;
    } else if (name === 'stage.end' && data.status === 'blocked' && summary.blocked === null) {
      summary.blocked = data.name ?? null;
    } else if (name === 'done') {
      summary.done = true;
      summary.override = data.answer_override ?? null;
      summary.sources = Array.isArray(data.sources) ? data.sources : [];
    }
  }
  return summary;
}

/** Signature `transformResponse` de promptfoo : (json, text) => chaîne JSON du résumé. */
function transformResponse(_json, text) {
  return JSON.stringify(summarize(text));
}

module.exports = { parseEvents, summarize, transformResponse };
