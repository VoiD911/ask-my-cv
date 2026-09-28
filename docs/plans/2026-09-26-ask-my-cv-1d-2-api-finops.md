# « Interroge mon CV » — plan 1d-2 : qualité de l'API et FinOps — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** coût facturé exact (tokens réellement comptés par le fournisseur), registre de dépenses qui ne bloque jamais la boucle d'événements et ne fait qu'une lecture par requête, traces sans aucune chaîne fournie par le visiteur, configuration stricte, tests de télémétrie indépendants des attributs privés d'OpenTelemetry.

**Architecture:** changements dans `ask-my-cv/src/ask_my_cv` uniquement, sans infrastructure nouvelle.
- Les fournisseurs LLM émettent, en fin de flux, un objet `TokenUsage` (tokens d'entrée/sortie comptés par le fournisseur, raison d'arrêt) en plus des morceaux de texte ; le pipeline facture ces valeurs quand elles existent, sinon l'estimation actuelle (flux interrompu, `FakeLLM`).
- `BudgetLedger.check` renvoie la dépense du jour (une seule lecture) ; `record` part dans l'exécuteur sans être attendu dans le chemin d'annulation.
- La configuration des exportateurs de traces devient une fonction pure, testée sans toucher aux internes d'OpenTelemetry.

**Tech Stack:** Python 3.12, FastAPI, boto3 (`ConverseStream`), OpenTelemetry, pydantic 2, pytest.

**Spec :** §3 (comptabilité, vie privée), §7 (FinOps). **Suivi :** section « Plan 1d » de `followups.md`. Le plan **1d-3** (évaluations LLM, red team nocturne, dérive, classifieur v1.2.0) suivra ; la LICENSE est traitée avec la publication (plan 1e).

## Faits vérifiés le 2026-09-26

- `ConverseStream` envoie, après le texte, un événement `messageStop {"stopReason": "end_turn" | "max_tokens" | "stop_sequence" | …}` puis un événement `metadata {"usage": {"inputTokens", "outputTokens", "totalTokens"}, "metrics": {"latencyMs"}}`. Le code actuel (`aws/bedrock.py`) les ignore.
- Ollama `/api/chat` en flux : le dernier objet (`"done": true`) porte `prompt_eval_count` (entrée) et `eval_count` (sortie), et `done_reason` (`stop`, `length`…).
- L'estimation actuelle `len(texte) // 4` est une règle de l'anglais ; en français, un token couvre en général moins de caractères, donc l'estimation sous-estime probablement le coût (écart réel mesuré à la tâche 5) et le plafond `daily_cap_usd` serait atteint plus tard que prévu.
- `StageBlocked("unknown_model", model=model_id)` place l'identifiant envoyé par le visiteur (≤ 64 caractères) dans les attributs du span (`xops.model`), exportés vers CloudWatch et Langfuse.
- `tests/test_telemetry.py` lit `exporter._client._headers`, `exporter._client._transport._session`, `exporter._client._timeout` : attributs privés, cassables à chaque mise à jour d'OpenTelemetry (Dependabot va proposer ces mises à jour).
- `Settings` accepte les clés inconnues : une faute (`cors_origin`) passe inaperçue.

## Contexte d'exécution

- Dépôt `<poste>\ask-my-cv`, branche `main`, identité git réglée, pas de ligne d'attribution, **ne pas pousser** (tâche 5, contrôleur).
- `export UV=~/AppData/Roaming/Python/Python314/Scripts/uv.exe`.
- Porte avant chaque commit : `$UV run ruff format . && $UV run ruff check . && $UV run pyright && $UV run pytest -q` (227 tests au départ).
- Aucun appel AWS dans les tâches 1 à 4 (Stubber / faux clients, comme aujourd'hui).
- Lire les tests existants voisins avant d'écrire les nouveaux : réutiliser les fixtures (`make_deps`, `spans`, faux clients Bedrock de `tests/test_aws_bedrock.py`).

## Structure des fichiers

| Fichier | Changement |
|---|---|
| `src/ask_my_cv/llm.py` | `TokenUsage`, `Chunk = str \| TokenUsage`, `FakeLLM` / `OllamaLLM` |
| `src/ask_my_cv/aws/bedrock.py` | `messageStop` + `metadata` → `TokenUsage` |
| `src/ask_my_cv/pipeline.py` | facturation réelle, `record` hors boucle, une lecture de quota, pas de chaîne visiteur dans les spans |
| `src/ask_my_cv/budget.py`, `src/ask_my_cv/aws/dynamo.py` | `check` renvoie la dépense du jour |
| `src/ask_my_cv/telemetry.py` | `exporter_config()` pure |
| `src/ask_my_cv/settings.py` | `extra="forbid"`, bornes, schéma d'URL |
| `tests/…` | tests correspondants |

---

### Task 1 : tokens réellement comptés par le fournisseur

**Files:** Modify `src/ask_my_cv/llm.py`, `src/ask_my_cv/aws/bedrock.py`, `src/ask_my_cv/pipeline.py`, `tests/test_llm.py`, `tests/test_aws_bedrock.py`, `tests/test_pipeline.py`

- [ ] **Step 1 : type** — dans `llm.py` :

```python
@dataclass(frozen=True)
class TokenUsage:
    """Consommation comptée par le fournisseur, émise en dernier dans le flux."""

    tokens_in: int
    tokens_out: int
    stop_reason: str | None = None


Chunk = str | TokenUsage
```

Le Protocol devient `def stream(self, system: str, user: str) -> AsyncGenerator[Chunk, None]: ...`. `FakeLLM` accepte un paramètre `usage: TokenUsage | None = None` et, s'il est fourni, l'émet après le texte (sinon rien : le pipeline estimera).

- [ ] **Step 2 : tests fournisseurs**
  - `tests/test_aws_bedrock.py` : le faux flux ConverseStream se termine par `{"messageStop": {"stopReason": "max_tokens"}}` puis `{"metadata": {"usage": {"inputTokens": 812, "outputTokens": 57, "totalTokens": 869}, "metrics": {"latencyMs": 900}}}` ; le flux de `BedrockLLM` produit les textes puis `TokenUsage(812, 57, "max_tokens")` en dernier. Un flux sans `metadata` (coupé) ne produit pas de `TokenUsage`.
  - `tests/test_llm.py` : Ollama — la dernière ligne NDJSON `{"done": true, "done_reason": "stop", "prompt_eval_count": 120, "eval_count": 30}` produit `TokenUsage(120, 30, "stop")` ; sans ces champs, rien.

- [ ] **Step 3 : implémentation fournisseurs**
  - Bedrock (thread de pompage) : mémoriser `stopReason` de `messageStop` ; sur `metadata.usage`, `send("usage", TokenUsage(inputTokens, outputTokens, stop_reason))` ; côté générateur, `kind == "usage"` → `yield value`.
  - Ollama : sur `chunk.get("done")`, si `prompt_eval_count`/`eval_count` sont présents, `yield TokenUsage(...)` avant `break`.

- [ ] **Step 4 : tests pipeline** (`tests/test_pipeline.py`)

```python
async def test_reported_usage_is_billed_instead_of_the_estimate(make_deps) -> None:
    pricey = FakeLLM(
        id="pricey",
        pricing=ModelPricing(input_per_mtok=1.0, output_per_mtok=5.0),
        usage=TokenUsage(tokens_in=1000, tokens_out=100, stop_reason="end_turn"),
    )
    ledger = InMemoryLedger(daily_cap_usd=1.0, per_visitor_limit=10, window_s=3600)
    events = await run(make_deps(providers={"pricey": pricey}, ledger=ledger))
    result = done(events)
    assert (result.tokens_in, result.tokens_out) == (1000, 100)
    assert result.cost_usd == round((1000 * 1.0 + 100 * 5.0) / 1_000_000, 6)


async def test_usage_source_and_stop_reason_are_traced(make_deps, spans) -> None:
    llm = FakeLLM(id="fake:echo", usage=TokenUsage(10, 5, "max_tokens"))
    await run(make_deps(providers={"fake:echo": llm}))
    [llm_span] = [s for s in spans.get_finished_spans() if s.name == "llm"]
    assert llm_span.attributes["xops.usage_source"] == "reported"
    assert llm_span.attributes["xops.stop_reason"] == "max_tokens"


async def test_without_reported_usage_the_estimate_is_kept(make_deps, spans) -> None:
    await run(make_deps())
    [llm_span] = [s for s in spans.get_finished_spans() if s.name == "llm"]
    assert llm_span.attributes["xops.usage_source"] == "estimated"
```

  Vérifier le nom exact des attributs produits par `StageRecorder.set` (préfixe `xops.`) et adapter.

- [ ] **Step 5 : pipeline**
  - `_stream_llm` : chaque morceau `TokenUsage` est mis de côté (dernier gagnant), jamais ajouté au texte ni compté dans `llm.progress`.
  - `Account` devient `Callable[[LLMProvider, str, TokenUsage | None], None]` ; les trois appels passent l'usage reçu (ou `None` si le flux a été coupé avant).
  - `account` : si `reported` est fourni, `tokens_in, tokens_out = reported.tokens_in, reported.tokens_out` et `recorder.set(usage_source="reported", stop_reason=reported.stop_reason or "")`, sinon estimation actuelle et `usage_source="estimated"`. Pour une bascule, c'est la dernière tentative qui fixe les attributs ; les coûts s'additionnent comme aujourd'hui.
  - Docstring de `estimate_tokens` : « repli quand le fournisseur ne compte pas (flux coupé, FakeLLM) ».
- [ ] **Step 6 : porte verte, commit** — `feat: coût facturé sur les tokens comptés par le fournisseur`

---

### Task 2 : registre — une lecture par requête, écriture hors de la boucle

**Files:** Modify `src/ask_my_cv/budget.py`, `src/ask_my_cv/aws/dynamo.py`, `src/ask_my_cv/pipeline.py`, `src/ask_my_cv/container.py` (commentaire des délais), `tests/test_budget.py`, `tests/test_aws_dynamo_ledger.py`, `tests/test_pipeline.py`

- [ ] **Step 1 : tests**
  - `check` renvoie la dépense du jour : `InMemoryLedger` (après `record("p", 0.25, t)`, `check("v", t) == 0.25`) et `DynamoLedger` (moto : même scénario ; et **une seule** lecture `GetItem` par `check` — compter les appels avec un client enveloppé ou `Stubber`).
  - Pipeline : l'étape `quota` n'appelle plus `spent_today` (un faux registre qui lève dans `spent_today` ne casse rien) et `spent_today_usd` vient de `check`.
  - `record` hors boucle :

```python
async def test_ledger_record_runs_off_the_event_loop(make_deps) -> None:
    loop_thread = threading.get_ident()
    seen: list[int] = []

    class ThreadSpy(InMemoryLedger):
        def record(self, provider_id: str, cost_usd: float, now: float) -> None:
            seen.append(threading.get_ident())
            super().record(provider_id, cost_usd, now)

    await run(make_deps(ledger=ThreadSpy(daily_cap_usd=1.0, per_visitor_limit=10, window_s=3600)))
    assert seen and all(t != loop_thread for t in seen)
```

  Les tests existants qui lisent le registre juste après `run` (`test_cost_is_recorded_in_ledger`, `test_client_disconnect_still_bills_generated_tokens`) doivent rester verts : voir Step 2 pour l'attente en fin de pipeline ; pour le chemin d'annulation, attendre dans le test (boucle courte `await asyncio.sleep(0.01)` jusqu'à ce que la dépense soit > 0, 2 s max).

- [ ] **Step 2 : implémentation**
  - Protocol `BudgetLedger.check(self, visitor: str, now: float) -> float` ; `InMemoryLedger.check` renvoie `self._spent(now)` (calculé sous le verrou) ; `DynamoLedger.check` renvoie la valeur déjà lue pour le contrôle du plafond. `spent_today` reste (utilisé ailleurs ? vérifier ; sinon le garder pour l'API publique du registre).
  - Pipeline, étape `quota` : `spent = await asyncio.to_thread(deps.ledger.check, visitor, now())`, plus d'appel à `spent_today`.
  - `account` : au lieu d'appeler `deps.ledger.record` directement, `future = loop.run_in_executor(None, deps.ledger.record, provider.id, cost, now())` ; `future.add_done_callback(_log_record_failure)` (journalise l'exception comme aujourd'hui, sans la relancer) ; garder une référence dans `pending: set[asyncio.Future]` (retirée au `done`) pour qu'elle ne soit pas collectée.
  - Fin normale du pipeline (après l'étape `output_guard`, avant `Done`) : `if pending: await asyncio.wait(pending, timeout=settings.stage_timeout_s)` — les dépenses sont écrites avant la réponse finale, sans bloquer la boucle. Dans le chemin d'annulation, **ne pas attendre** : les écritures continuent dans leur thread.
  - `container.py` : mettre à jour le commentaire au-dessus de `_TIMEOUTS` (il indique que `record` est encore synchrone).
- [ ] **Step 3 : porte verte, commit** — `fix: registre en une lecture par requête et écritures hors de la boucle d'événements`

---

### Task 3 : traces sans chaîne visiteur, tests de télémétrie robustes

**Files:** Modify `src/ask_my_cv/pipeline.py`, `src/ask_my_cv/telemetry.py`, `tests/test_pipeline.py`, `tests/test_telemetry.py`

- [ ] **Step 1 : tests vie privée** — étendre `test_spans_never_carry_the_question_or_the_visitor` en un test paramétré sur trois scénarios (question normale, injection bloquée, modèle inconnu `model="modele-du-visiteur-xyz"`) qui vérifie que ni la question, ni l'identifiant visiteur, ni `"modele-du-visiteur-xyz"` n'apparaissent dans : les valeurs d'attributs des spans, les **noms** de spans, les **descriptions de statut**, les **événements** de spans (nom + attributs), et les attributs `attrs` des événements SSE `stage.end` (le texte de la réponse `answer` est exclu, c'est son rôle).
- [ ] **Step 2 : correction** — `StageBlocked("unknown_model")` sans l'identifiant ; si une information est utile, `model_len=len(model_id)` seulement. `reception` ne pose `model=` qu'après validation (identifiant connu). Chercher tout autre `StageBlocked(..., key=<valeur visiteur>)`.
- [ ] **Step 3 : télémétrie** — extraire de `exporter_for` une fonction pure :

```python
@dataclass(frozen=True)
class ExporterConfig:
    endpoint: str
    headers: dict[str, str]
    timeout_s: float
    sigv4: bool  # True : session signée SigV4 (service xray)


def exporter_config(name: str, settings: Settings) -> ExporterConfig: ...
```

  `exporter_for` construit l'`OTLPSpanExporter` à partir de cette configuration (et de `SigV4Session` si `sigv4`). Réécrire `tests/test_telemetry.py` pour tester `exporter_config` (en-tête `Authorization: Basic …` de Langfuse, `x-langfuse-ingestion-version`, point d'entrée X-Ray de la région, `timeout_s <= 2.0`, identifiants manquants → `ConfigError`) ; garder **un** test de fumée qui construit réellement l'exportateur (sans lire d'attribut privé : `isinstance` suffit), et un test de `SigV4Session` lui-même (signature d'une requête préparée : en-tête `Authorization` qui commence par `AWS4-HMAC-SHA256`).
- [ ] **Step 4 : porte verte, commit** — `fix: aucune chaîne du visiteur dans les traces ; tests de télémétrie sans attributs privés`

---

### Task 4 : configuration stricte

**Files:** Modify `src/ask_my_cv/settings.py`, `tests/test_settings.py`, `README.md`

- [ ] **Step 1 : tests** — `settings.yaml` avec une clé inconnue (`cors_origin`) → `ConfigError` dont le message nomme la clé (`cors_origin`) sans valeur ; même chose dans un élément de `models` ; `embed_dim: 5000` → erreur ; `ollama_url: "file:///etc/passwd"` → erreur ; `ollama_url: "https://ollama.internal:11434"` → accepté. Les fichiers réels `settings.yaml` et `settings.aws.yaml` se chargent toujours (test existant ou nouveau).
- [ ] **Step 2 : implémentation** — `model_config = ConfigDict(extra="forbid")` sur `Settings` et `ModelConfig` ; `embed_dim: int = Field(default=256, ge=1, le=4096)` ; validateur `ollama_url` : schéma `http` ou `https`, hôte non vide (`urllib.parse`). Vérifier que le formatage des erreurs de `load_settings` (`include_input=False`) nomme bien la clé en trop (`extra_forbidden`, `loc`) sans afficher la valeur.
- [ ] **Step 3 : README** — la commande de test devient `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright`.
- [ ] **Step 4 : porte verte, commit** — `fix: configuration stricte (clés inconnues refusées, bornes, schéma d'URL)`

---

### Task 5 : mise en service et vérification réelle (contrôleur, avec accord)

- [ ] Revue finale (sous-agent, lecture seule) de `git diff <début>..HEAD`.
- [ ] Pousser `main` (accord). CI : `security`, `test`, `terraform`, `deploy` verts (le déploiement signé et le retour arrière existent depuis 1d-1).
- [ ] Dans la sortie du test de fumée de production : `coût` non nul. Dans CloudWatch (`aws/spans`, `filter-log-events` sur le `trace_id` du test) : le span `llm` porte `xops.usage_source = reported` et `xops.stop_reason`. Comparer `tokens_in` réel à l'ancienne estimation (≈ `len/4`) et noter l'écart dans le suivi.

### Task 6 : documentation et suivi (contrôleur)

- [ ] `followups.md` : barrer « Coût exact », « Modèle inconnu dans les traces », « Tests de télémétrie fragiles », « Test de vie privée », « Quota », « Configuration », « README … `ruff format --check` », et le point `ledger.record` des revues 1c-2 ; créer la section « Plan 1d-3 » (évaluations LLM, red team nocturne, dérive PSI, v1.2.0 du classifieur, promptfoo « information absente ») ; LICENSE déplacée en 1e.
- [ ] README (section Production) : le coût affiché est désormais celui compté par Bedrock ; mention de `usage_source`.
- [ ] Commits séparés, push avec accord.

## Critères de fin

- En production, le coût d'une question provient des tokens comptés par Bedrock (`usage_source = reported`), et la raison d'arrêt est tracée.
- L'étape `quota` fait une seule lecture DynamoDB ; aucune écriture du registre ne s'exécute dans la boucle d'événements.
- Aucune chaîne fournie par le visiteur (question, identifiant, modèle demandé) dans les spans (attributs, noms, statuts, événements) ni dans les `attrs` SSE.
- Une clé inconnue dans la configuration empêche le démarrage, avec un message qui la nomme.
- `tests/test_telemetry.py` ne lit plus aucun attribut privé.
- 227 tests + les nouveaux, `ruff`, `pyright` : tout vert.
