'use strict';

/**
 * Fournisseur promptfoo personnalisé pour `POST /ask`.
 *
 * Pourquoi pas le fournisseur `https` intégré : l'OAC CloudFront -> Lambda Function URL
 * exige, pour tout POST, l'en-tête `x-amz-content-sha256` égal au SHA-256 hexadécimal du
 * corps exact envoyé, que promptfoo ne sait pas calculer. Ce fournisseur construit le
 * corps, le hache, l'envoie, lit le flux SSE et renvoie le résumé de `sse.js` (chaîne JSON,
 * complétée du statut HTTP : une 422 reste un résultat vérifiable, pas une erreur).
 *
 * config :
 *   urlEnv          variable d'environnement qui porte l'URL (ou sa base, voir `path`)
 *   path            suffixe ajouté à cette URL (ex. `/api/ask` derrière SITE_URL)
 *   defaultUrl      URL si la variable est absente
 *   requireEvalToken  échouer si EVAL_TOKEN est absent (suite de nuit)
 *   timeoutMs       délai par requête (90 s par défaut)
 */

const crypto = require('node:crypto');
const { summarize } = require('./sse');

class AskProvider {
  constructor(options = {}) {
    this.providerId = options.id || 'ask-my-cv';
    this.config = options.config || {};
  }

  id() {
    return this.providerId;
  }

  url() {
    const { urlEnv, path = '', defaultUrl } = this.config;
    const fromEnv = urlEnv ? process.env[urlEnv] : undefined;
    const base = fromEnv || defaultUrl;
    if (!base) throw new Error(`URL de l'API absente (variable ${urlEnv} non définie)`);
    return base.replace(/\/+$/, '') + path;
  }

  async callApi(prompt) {
    const token = process.env.EVAL_TOKEN;
    if (this.config.requireEvalToken && !token) {
      return { error: 'EVAL_TOKEN absent : la suite de nuit exige le jeton d\'évaluation' };
    }
    const body = JSON.stringify({ question: prompt });
    const headers = {
      'content-type': 'application/json',
      'x-amz-content-sha256': crypto.createHash('sha256').update(body, 'utf8').digest('hex'),
    };
    if (token) headers['x-eval-token'] = token;
    try {
      const response = await fetch(this.url(), {
        method: 'POST',
        headers,
        body,
        signal: AbortSignal.timeout(this.config.timeoutMs ?? 90_000),
      });
      const text = await response.text();
      const ok = response.ok && (response.headers.get('content-type') || '').startsWith('text/event-stream');
      const summary = ok ? summarize(text) : summarize('');
      return { output: JSON.stringify({ status: response.status, ...summary }) };
    } catch (err) {
      return { error: `requête vers /ask en échec : ${err && err.message ? err.message : err}` };
    }
  }
}

module.exports = AskProvider;
