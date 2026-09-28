# « Interroge mon CV » — plan 1c-1b : adaptateurs AWS — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** brancher l'API sur AWS derrière les interfaces existantes — Claude via Bedrock (`ConverseStream`), embeddings Titan V2, recherche vectorielle DynamoDB, registre de budget DynamoDB atomique, traces OpenTelemetry vers CloudWatch (OTLP signé SigV4) et Langfuse — le tout testé sans compte AWS, le mode local restant inchangé.

**Architecture:** un sous-paquet `ask_my_cv.aws` isole boto3. Chaque adaptateur reçoit un client boto3 injecté (tests : faux client, `botocore.stub.Stubber` ou moto). Les appels boto3 synchrones passent par `asyncio.to_thread` ; le flux Bedrock est pompé dans un thread vers une `asyncio.Queue`. `settings.aws.yaml` décrit la configuration de production (utilisée au plan 1c-2).

**Tech Stack:** boto3 ≥ 1.43.64 (API `SearchVectors`), opentelemetry-exporter-otlp-proto-http, botocore SigV4, moto (tests).

**Spec :** §2.1 (région `ca-central-1`, Bedrock profil `us.`, Titan V2, DynamoDB, traces), §3 (vie privée). **Suivi :** section « Plan 1c-1b » de `followups.md`.

## Faits vérifiés le 2026-09-25

- boto3 1.43.103 : `dynamodb.search_vectors(TableName, IndexName, SearchVector, TopK, …)` ; `SearchVector` est une **liste de valeurs** `[{"N": "0.12"}, …]` (pas `{"L": …}`) ; réponse `SearchResults[{Item, Score}]`. `CreateTable` accepte `VectorIndexes` (`DistanceFunction` : `COSINE | DOT_PRODUCT | EUCLIDEAN`). Vecteurs réservés aux tables on-demand.
- **moto 5.2.3 ne gère pas `SearchVectors`** → tests par `Stubber` (valide chaque requête contre le modèle de service réel). moto gère `UpdateItem` conditionnel et `ADD` → tests du registre.
- Bedrock `bedrock-runtime` : `ConverseStream` disponible. Claude Haiku 4.5 via le profil `us.anthropic.claude-haiku-4-5-20251001-v1:0` (≈ 1 $ / 5 $ par million de tokens, + ~10 % en inter-régions).
- **Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`) est disponible en région dans `ca-central-1`** (fiche Bedrock) : les embeddings restent au Canada.
- Langfuse US : `https://us.cloud.langfuse.com/api/public/otel/v1/traces`, OTLP **HTTP** uniquement, `Authorization: Basic base64(pk:sk)`, en-tête `x-langfuse-ingestion-version: 4`.
- CloudWatch / X-Ray accepte l'OTLP signé SigV4 (service `xray`, `https://xray.<région>.amazonaws.com/v1/traces`) ; l'activation côté compte (Transaction Search) relève du plan 1c-2.
- Sur ce poste, un profil AWS local casse la création des clients boto3 dans les tests : **les tests doivent isoler l'environnement AWS** (tâche 0).

## Contexte d'exécution

- Dépôt `<poste>\ask-my-cv`, branche `main`, identité git réglée, pas de ligne d'attribution, ne pas pousser.
- `export UV=~/AppData/Roaming/Python/Python314/Scripts/uv.exe`.
- Avant chaque commit : `$UV run ruff format . && $UV run ruff check . && $UV run pyright && $UV run pytest -q`, tout vert (169 tests au départ).
- **Aucun appel réseau vers AWS** dans les tests ni pendant l'exécution de ce plan.

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `src/ask_my_cv/aws/__init__.py` | sous-paquet AWS |
| `src/ask_my_cv/aws/bedrock.py` | `BedrockLLM` (ConverseStream), `BedrockEmbedder` (Titan V2) |
| `src/ask_my_cv/aws/dynamo.py` | `DynamoVectorStore`, `DynamoLedger` |
| `src/ask_my_cv/aws/sigv4.py` | `SigV4Session` (requests signées) |
| `src/ask_my_cv/telemetry.py` | `build_tracer_provider`, `configure_tracing` |
| `src/ask_my_cv/settings.py` | réglages AWS et traces |
| `src/ask_my_cv/container.py` | fabriques AWS |
| `src/ask_my_cv/app.py` | vidage des traces en fin de requête |
| `src/ask_my_cv/ingest.py` | `--target dynamodb` |
| `settings.aws.yaml` | configuration de production (plan 1c-2) |

---

### Task 0 : dépendances et environnement AWS de test

**Files:** Modify `pyproject.toml`, `tests/conftest.py`

- [ ] **Step 1** — `pyproject.toml` : ajouter aux `dependencies` `"boto3>=1.43.64"` et `"opentelemetry-exporter-otlp-proto-http>=1.27"` ; au groupe `dev` : `"moto[dynamodb]>=5.1"`. `$UV sync --group ml`.
- [ ] **Step 2** — `tests/conftest.py` : fixture `autouse` qui isole AWS pour **tous** les tests :

```python
@pytest.fixture(autouse=True)
def isolated_aws(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Jamais de profil ni d'identifiants réels : aucun test ne peut joindre AWS."""
    empty = tmp_path_factory.getbasetemp() / "aws-empty"
    empty.mkdir(exist_ok=True)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(empty / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(empty / "credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ca-central-1")
```

- [ ] **Step 3** — test de fumée `tests/test_aws_env.py` :

```python
import boto3


def test_boto3_clients_are_isolated() -> None:
    client = boto3.client("dynamodb", region_name="ca-central-1")
    assert "SearchVectors" in client.meta.service_model.operation_names
    assert client._request_signer._credentials.access_key == "testing"
```

- [ ] **Step 4** — vérifier (tout vert) et commit : `chore: dépendances AWS et isolation AWS des tests`.

---

### Task 1 : réglages AWS et configuration de production

**Files:** Modify `src/ask_my_cv/settings.py` ; Create `settings.aws.yaml` ; Test `tests/test_settings.py`

- [ ] **Step 1 : tests**

```python
def test_bedrock_model_requires_a_model_id() -> None:
    data = minimal()
    data["models"].append({"id": "bedrock:x", "provider": "bedrock"})
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


@pytest.mark.parametrize("dim", [0, 300, 2048])
def test_bedrock_embedder_needs_a_titan_dimension(dim: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(minimal(embedder="bedrock", embed_dim=dim))


def test_production_aws_settings_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISITOR_SALT", "s" * 48)
    settings = load_settings(Path("settings.aws.yaml"))
    assert (settings.environment, settings.aws_region) == ("prod", "ca-central-1")
    assert (settings.embedder, settings.vector_store, settings.ledger) == ("bedrock", "dynamodb", "dynamodb")
    assert settings.trusted_proxy == "cloudfront" and settings.detector == "onnx"
    assert set(settings.tracing) == {"cloudwatch", "langfuse"}
    haiku = next(m for m in settings.models if m.provider == "bedrock")
    assert haiku.model.startswith("us.anthropic.claude-haiku-4-5")
```

- [ ] **Step 2 : implémenter**
  - `ModelConfig.provider` : `Literal["fake", "ollama", "bedrock"]` ; le validateur existant exige `model` pour `ollama` **et** `bedrock`.
  - `Settings` (nouveaux champs) :

```python
    aws_region: str = "ca-central-1"
    embedder: Literal["hash", "bedrock"] = "hash"
    embed_model: str = "amazon.titan-embed-text-v2:0"
    vector_store: Literal["file", "dynamodb"] = "file"
    chunks_table: str = "ask-my-cv-chunks"
    ledger: Literal["memory", "dynamodb"] = "memory"
    ledger_table: str = "ask-my-cv-ledger"
    tracing: list[Literal["console", "cloudwatch", "langfuse"]] = []
    langfuse_endpoint: str = "https://us.cloud.langfuse.com/api/public/otel/v1/traces"
```

  `embed_dim` : `Field(default=256, ge=1)` ; validateur : si `embedder == "bedrock"`, `embed_dim` ∈ {256, 512, 1024}.
  - `settings.aws.yaml` :

```yaml
# Configuration de production (AWS, ca-central-1). Secrets par variables d'environnement :
# VISITOR_SALT, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY.
environment: prod
trusted_proxy: cloudfront
aws_region: ca-central-1
prompt_path: prompts/<adresse>
detector: onnx
model_manifest: models/prod.json
embedder: bedrock
embed_model: amazon.titan-embed-text-v2:0
embed_dim: 1024
vector_store: dynamodb
chunks_table: ask-my-cv-chunks
ledger: dynamodb
ledger_table: ask-my-cv-ledger
tracing: [cloudwatch, langfuse]
default_model: bedrock:haiku-4.5
fallback_chain: [bedrock:haiku-4.5]
models:
  - id: bedrock:haiku-4.5
    provider: bedrock
    model: us.anthropic.claude-haiku-4-5-20251001-v1:0   # profil d'inférence US : requêtes traitées aux États-Unis
    public: true
    input_per_mtok: 1.1      # tarif Haiku 4.5 + ~10 % inter-régions
    output_per_mtok: 5.5
top_k: 5
injection_threshold: 0.5
daily_cap_usd: 0.5
per_visitor_limit: 10
visitor_window_s: 3600
stage_timeout_s: 10
first_token_timeout_s: 8
llm_deadline_s: 25
allowed_contacts: [alex.martin@example.com]
cors_origins: []          # origine du site (plan 1e)
```

- [ ] **Step 3** — vérifier, commit : `feat: réglages AWS et configuration de production`.

---

### Task 2 : Bedrock — Claude en streaming et embeddings Titan

**Files:** Create `src/ask_my_cv/aws/__init__.py` (vide), `src/ask_my_cv/aws/bedrock.py` ; Test `tests/test_aws_bedrock.py`

- [ ] **Step 1 : tests**

```python
import asyncio
import io
import json
import time
from typing import Any

import pytest
from botocore.exceptions import ClientError

from ask_my_cv.aws.bedrock import BedrockEmbedder, BedrockLLM
from ask_my_cv.llm import LLMError


def delta(text: str) -> dict:
    return {"contentBlockDelta": {"delta": {"text": text}, "contentBlockIndex": 0}}


class FakeRuntime:
    def __init__(self, events: list[dict] | None = None, error: Exception | None = None, pause_s: float = 0.0) -> None:
        self.events, self.error, self.pause_s = events or [], error, pause_s
        self.calls: list[dict[str, Any]] = []
        self.consumed = 0

    def converse_stream(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        if self.error:
            raise self.error

        def stream():
            for event in self.events:
                if self.pause_s:
                    time.sleep(self.pause_s)
                self.consumed += 1
                yield event

        return {"stream": stream()}

    def invoke_model(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        dims = json.loads(kwargs["body"])["dimensions"]
        return {"body": io.BytesIO(json.dumps({"embedding": [0.5] * dims}).encode())}


async def collect(llm: BedrockLLM) -> list[str]:
    return [piece async for piece in llm.stream("système", "question")]


async def test_stream_yields_text_deltas_and_sends_a_converse_request() -> None:
    runtime = FakeRuntime([{"messageStart": {"role": "assistant"}}, delta("Bon"), delta("jour [1]"), {"messageStop": {}}])
    llm = BedrockLLM(id="bedrock:haiku", model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0", client=runtime)
    assert await collect(llm) == ["Bon", "jour [1]"]
    call = runtime.calls[0]
    assert call["modelId"].startswith("us.anthropic.claude-haiku")
    assert call["system"] == [{"text": "système"}]
    assert call["messages"] == [{"role": "user", "content": [{"text": "question"}]}]
    assert call["inferenceConfig"]["temperature"] == 0.0


async def test_client_error_becomes_llm_error() -> None:
    error = ClientError({"Error": {"Code": "ThrottlingException", "Message": "lent"}}, "ConverseStream")
    with pytest.raises(LLMError):
        await collect(BedrockLLM(id="b", model_id="m", client=FakeRuntime(error=error)))


async def test_stream_error_event_becomes_llm_error() -> None:
    runtime = FakeRuntime([delta("x"), {"modelStreamErrorException": {"message": "coupé"}}])
    with pytest.raises(LLMError):
        await collect(BedrockLLM(id="b", model_id="m", client=runtime))


async def test_closing_the_stream_stops_the_pump() -> None:
    runtime = FakeRuntime([delta("a")] * 100, pause_s=0.01)
    llm = BedrockLLM(id="b", model_id="m", client=runtime)
    stream = llm.stream("s", "u")
    assert await anext(stream) == "a"
    await stream.aclose()
    await asyncio.sleep(0.1)
    consumed = runtime.consumed
    await asyncio.sleep(0.1)
    assert runtime.consumed == consumed < 100


async def test_titan_embedder_requests_normalized_vectors() -> None:
    runtime = FakeRuntime()
    embedder = BedrockEmbedder("amazon.titan-embed-text-v2:0", runtime, dim=1024)
    [vector] = await embedder.embed(["Quelle expérience ?"])
    assert len(vector) == 1024
    body = json.loads(runtime.calls[0]["body"])
    assert body == {"inputText": "Quelle expérience ?", "dimensions": 1024, "normalize": True}
```

- [ ] **Step 2 : implémenter `src/ask_my_cv/aws/bedrock.py`**

```python
from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncGenerator
from typing import Any

from ask_my_cv.llm import LLMError, ModelPricing


class BedrockLLM:
    """Claude sur Bedrock (ConverseStream). Le flux boto3 synchrone est pompé dans un thread."""

    def __init__(
        self,
        id: str,
        model_id: str,
        client: Any,
        pricing: ModelPricing | None = None,
        max_tokens: int = 400,
    ) -> None:
        self.id = id
        self.model_id = model_id
        self.pricing = pricing or ModelPricing()
        self.max_tokens = max_tokens
        self._client = client

    async def stream(self, system: str, user: str) -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        stop = threading.Event()

        def send(kind: str, value: Any) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (kind, value))
            except RuntimeError:  # boucle fermée : plus personne n'écoute
                pass

        def pump() -> None:
            try:
                response = self._client.converse_stream(
                    modelId=self.model_id,
                    system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": user}]}],
                    inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0.0},
                )
                for event in response["stream"]:
                    if stop.is_set():
                        return
                    error = next((key for key in event if key.endswith("Exception")), None)
                    if error:
                        raise LLMError(f"{self.id} : {error}")
                    text = event.get("contentBlockDelta", {}).get("delta", {}).get("text")
                    if text:
                        send("text", text)
                send("end", None)
            except Exception as exc:  # botocore, réseau, événement d'erreur
                send("error", exc)

        threading.Thread(target=pump, name=f"bedrock-{self.id}", daemon=True).start()
        try:
            while True:
                kind, value = await queue.get()
                if kind == "text":
                    yield value
                elif kind == "end":
                    return
                else:
                    raise LLMError(f"{self.id} : {type(value).__name__}") from value
        finally:
            stop.set()  # le thread s'arrête au prochain événement ; aucune attente réseau ici


class BedrockEmbedder:
    """Titan Text Embeddings V2 (disponible en région dans ca-central-1)."""

    def __init__(self, model_id: str, client: Any, dim: int = 1024) -> None:
        self.model_id = model_id
        self.dim = dim
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [await asyncio.to_thread(self._embed_one, text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        response = self._client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": self.dim, "normalize": True}),
        )
        vector = json.loads(response["body"].read())["embedding"]
        if len(vector) != self.dim:
            raise ValueError(f"{self.model_id} : {len(vector)} dimensions au lieu de {self.dim}")
        return [float(v) for v in vector]
```

- [ ] **Step 3** — vérifier (lancer `tests/test_aws_bedrock.py` 3 fois : pas d'instabilité), commit : `feat(aws): Claude via Bedrock ConverseStream et embeddings Titan V2`.

---

### Task 3 : recherche vectorielle DynamoDB et ingestion

**Files:** Create `src/ask_my_cv/aws/dynamo.py` ; Modify `src/ask_my_cv/ingest.py` ; Test `tests/test_aws_dynamo_vectors.py`

- [ ] **Step 1 : tests** (le `Stubber` valide chaque requête contre le modèle de service réel)

```python
import boto3
from botocore.stub import Stubber

from ask_my_cv.aws.dynamo import INDEX_NAME, DynamoVectorStore
from ask_my_cv.vectorstore import Chunk


def item(id: str, section: str, text: str) -> dict:
    return {"id": {"S": id}, "section": {"S": section}, "text": {"S": text}}


async def test_search_sends_a_vector_list_and_maps_results() -> None:
    client = boto3.client("dynamodb", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "search_vectors",
        {"SearchResults": [{"Item": item("c2", "Compétences", "Python"), "Score": 0.91},
                           {"Item": item("c1", "Expérience", "MLOps"), "Score": 0.42}]},
        {"TableName": "chunks", "IndexName": INDEX_NAME, "SearchVector": [{"N": "0.5"}, {"N": "-0.25"}], "TopK": 2},
    )
    with stub:
        hits = await DynamoVectorStore("chunks", client).search([0.5, -0.25], k=2)
    stub.assert_no_pending_responses()
    assert [(h.chunk.id, h.chunk.section, h.score) for h in hits] == [("c2", "Compétences", 0.91), ("c1", "Expérience", 0.42)]


def test_write_puts_chunks_with_their_embedding() -> None:
    client = boto3.client("dynamodb", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "put_item", {},
        {"TableName": "chunks", "Item": {**item("c1", "Expérience", "MLOps"), "embedding": {"L": [{"N": "0.5"}, {"N": "1.0"}]}}},
    )
    with stub:
        DynamoVectorStore("chunks", client).write([Chunk("c1", "Expérience", "MLOps")], [[0.5, 1.0]])
    stub.assert_no_pending_responses()
```

- [ ] **Step 2 : implémenter** (début de `src/ask_my_cv/aws/dynamo.py`)

```python
from __future__ import annotations

import asyncio
from typing import Any

from ask_my_cv.vectorstore import Chunk, Hit

INDEX_NAME = "embedding-index"


def _number(value: float) -> dict[str, str]:
    return {"N": repr(float(value))}


class DynamoVectorStore:
    """Recherche vectorielle native DynamoDB (API SearchVectors, table on-demand)."""

    def __init__(self, table: str, client: Any, index: str = INDEX_NAME) -> None:
        self.table = table
        self.index = index
        self._client = client

    async def search(self, vector: list[float], k: int) -> list[Hit]:
        return await asyncio.to_thread(self._search, vector, k)

    def _search(self, vector: list[float], k: int) -> list[Hit]:
        response = self._client.search_vectors(
            TableName=self.table,
            IndexName=self.index,
            SearchVector=[_number(v) for v in vector],
            TopK=k,
        )
        hits = []
        for result in response.get("SearchResults", []):
            found = result["Item"]
            chunk = Chunk(id=found["id"]["S"], section=found["section"]["S"], text=found["text"]["S"])
            hits.append(Hit(chunk=chunk, score=float(result.get("Score", 0.0))))
        return hits

    def write(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._client.put_item(
                TableName=self.table,
                Item={
                    "id": {"S": chunk.id},
                    "section": {"S": chunk.section},
                    "text": {"S": chunk.text},
                    "embedding": {"L": [_number(v) for v in vector]},
                },
            )
```

  (Si la représentation `repr(float(0.5))` = `"0.5"` et `repr(1.0)` = `"1.0"` diffère de ce qu'attend le test, ajuster le **test** à `repr` ; la représentation doit rester sans perte.)
- [ ] **Step 3 : ingestion** — `ingest.main` accepte `--target {file,dynamodb}` (défaut `file`) ; `dynamodb` : `DynamoVectorStore(settings.chunks_table, aws_client("dynamodb", settings)).write(chunks, vectors)` (fabrique `aws_client` de la tâche 6 : pour l'instant, l'importer paresseusement depuis `ask_my_cv.container` ; si la tâche 6 n'est pas faite, créer `aws_client` dès maintenant dans `container.py` avec le code donné en tâche 6). Le chemin `file` est inchangé. Test : `main(["--cv", …, "--target", "dynamodb"])` avec `monkeypatch` de `DynamoVectorStore.write` qui capture les passages → 3 passages écrits.
- [ ] **Step 4** — vérifier, commit : `feat(aws): recherche vectorielle DynamoDB et ingestion vers DynamoDB`.

---

### Task 4 : registre de budget DynamoDB atomique

**Files:** Modify `src/ask_my_cv/aws/dynamo.py`, `src/ask_my_cv/pipeline.py` ; Test `tests/test_aws_dynamo_ledger.py`, `tests/test_pipeline.py`

- [ ] **Step 1 : tests** (moto)

```python
import boto3
import pytest
from moto import mock_aws

from ask_my_cv.aws.dynamo import DynamoLedger
from ask_my_cv.budget import BudgetExceeded, RateLimited

T0 = 1_790_000_000.0


@pytest.fixture
def ledger():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ca-central-1")
        client.create_table(
            TableName="ledger", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        )
        yield DynamoLedger("ledger", client, daily_cap_usd=0.01, per_visitor_limit=2, window_s=60)


def test_rate_limit_is_atomic_per_fixed_window(ledger: DynamoLedger) -> None:
    ledger.check("v1", T0)
    ledger.check("v1", T0 + 1)
    with pytest.raises(RateLimited):
        ledger.check("v1", T0 + 2)
    ledger.check("v2", T0 + 2)
    ledger.check("v1", T0 + 60 - (T0 % 60) + 1)  # fenêtre suivante


def test_spend_accumulates_per_day_and_provider_then_blocks(ledger: DynamoLedger) -> None:
    ledger.record("bedrock:haiku", 0.006, T0)
    ledger.record("fake:echo", 0.0, T0)
    assert ledger.spent_today(T0) == pytest.approx(0.006)
    ledger.check("v1", T0)
    ledger.record("bedrock:haiku", 0.006, T0)
    assert ledger.spent_by_provider(T0) == {"bedrock:haiku": pytest.approx(0.012), "fake:echo": 0.0}
    with pytest.raises(BudgetExceeded):
        ledger.check("v1", T0)
    assert ledger.spent_today(T0 + 86_400) == 0.0


def test_items_carry_a_ttl(ledger: DynamoLedger) -> None:
    ledger.check("v1", T0)
    ledger.record("p", 0.001, T0)
    items = ledger._client.scan(TableName="ledger")["Items"]
    assert all(int(i["expires_at"]["N"]) > T0 for i in items)
```

  `tests/test_pipeline.py` :

```python
async def test_ledger_write_failure_does_not_break_the_answer(make_deps) -> None:
    class FlakyLedger(InMemoryLedger):
        def record(self, provider_id: str, cost_usd: float, now: float) -> None:
            raise RuntimeError("DynamoDB indisponible")

    deps = make_deps(ledger=FlakyLedger(daily_cap_usd=1.0, per_visitor_limit=10, window_s=3600))
    events = await run(deps)
    assert ends(events)[-1] == ("output_guard", "ok")
    assert len(answers(events)) == 1
```

- [ ] **Step 2 : implémenter `DynamoLedger`** (dans `dynamo.py`, importer `time`, `logging`, `BudgetExceeded`, `RateLimited`)

```python
def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now))


class DynamoLedger:
    """Quotas et dépenses dans DynamoDB : compteurs atomiques (ADD), écriture conditionnelle, TTL.

    Le quota visiteur est une fenêtre fixe (et non glissante comme en mémoire) : c'est ce qui
    permet un compteur atomique en une seule écriture conditionnelle.
    """

    def __init__(self, table: str, client: Any, daily_cap_usd: float, per_visitor_limit: int, window_s: float) -> None:
        self.table = table
        self.daily_cap_usd = daily_cap_usd
        self.per_visitor_limit = per_visitor_limit
        self.window_s = window_s
        self._client = client

    def check(self, visitor: str, now: float) -> None:
        if self.spent_today(now) >= self.daily_cap_usd:
            raise BudgetExceeded
        window = int(now // self.window_s)
        try:
            self._client.update_item(
                TableName=self.table,
                Key={"pk": {"S": f"rate#{visitor}#{window}"}},
                UpdateExpression="ADD #count :one SET #exp = :exp",
                ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
                ExpressionAttributeNames={"#count": "count", "#exp": "expires_at"},
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":limit": {"N": str(self.per_visitor_limit)},
                    ":exp": {"N": str(int(now + 2 * self.window_s))},
                },
            )
        except self._client.exceptions.ConditionalCheckFailedException:
            raise RateLimited from None

    def record(self, provider_id: str, cost_usd: float, now: float) -> None:
        self._client.update_item(
            TableName=self.table,
            Key={"pk": {"S": f"spend#{_day(now)}"}},
            UpdateExpression="ADD #total :cost, #provider :cost SET #exp = :exp",
            ExpressionAttributeNames={"#total": "total", "#provider": f"p#{provider_id}", "#exp": "expires_at"},
            ExpressionAttributeValues={
                ":cost": {"N": format(cost_usd, ".10f")},
                ":exp": {"N": str(int(now + 40 * 86_400))},
            },
        )

    def _spend_item(self, now: float) -> dict[str, Any]:
        response = self._client.get_item(
            TableName=self.table, Key={"pk": {"S": f"spend#{_day(now)}"}}, ConsistentRead=True
        )
        return response.get("Item", {})

    def spent_today(self, now: float) -> float:
        return float(self._spend_item(now).get("total", {}).get("N", "0"))

    def spent_by_provider(self, now: float) -> dict[str, float]:
        return {k[2:]: float(v["N"]) for k, v in self._spend_item(now).items() if k.startswith("p#")}
```

- [ ] **Step 3 : écriture du registre tolérante** — dans `pipeline.py`, la fonction `account` entoure `deps.ledger.record(...)` d'un `try/except Exception` qui journalise (`logger.warning("registre des dépenses indisponible", exc_info=True)`, `logger = logging.getLogger(__name__)`) ; les totaux `usage` restent mis à jour ; `CancelledError` n'est pas une `Exception` et n'est donc pas masquée.
- [ ] **Step 4** — vérifier, commit : `feat(aws): registre de budget DynamoDB atomique avec TTL, écriture du registre tolérante`.

---

### Task 5 : traces vers CloudWatch (SigV4) et Langfuse

**Files:** Create `src/ask_my_cv/aws/sigv4.py`, `src/ask_my_cv/telemetry.py` ; Test `tests/test_telemetry.py`

- [ ] **Step 1 : tests**

```python
import base64

import pytest
import requests
from botocore.credentials import Credentials

from ask_my_cv.aws.sigv4 import SigV4Session
from ask_my_cv.settings import ConfigError, ModelConfig, Settings
from ask_my_cv.telemetry import build_tracer_provider, exporter_for


class Capture(requests.adapters.BaseAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.request: requests.PreparedRequest | None = None

    def send(self, request, **kwargs):  # type: ignore[override]
        self.request = request
        response = requests.Response()
        response.status_code = 200
        response._content = b""
        return response

    def close(self) -> None:
        pass


def settings(**extra) -> Settings:
    return Settings(
        models=[ModelConfig(id="fake:echo", provider="fake")], default_model="fake:echo",
        fallback_chain=["fake:echo"], **extra,
    )


def test_sigv4_session_signs_for_xray() -> None:
    session = SigV4Session("ca-central-1", "xray", Credentials("AKIDEXAMPLE", "secret"))
    capture = Capture()
    session.mount("https://", capture)
    session.headers.update({"Content-Type": "application/x-protobuf"})
    session.post("https://xray.ca-central-1.amazonaws.com/v1/traces", data=b"\x0a\x00")
    assert capture.request is not None
    auth = capture.request.headers["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
    assert "/ca-central-1/xray/aws4_request" in auth
    assert "X-Amz-Date" in capture.request.headers


def test_no_tracing_means_no_provider() -> None:
    assert build_tracer_provider(settings()) is None


def test_langfuse_exporter_uses_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "<test-key>")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "<test-key>")
    exporter = exporter_for("langfuse", settings(tracing=["langfuse"]))
    expected = base64.b64encode(b"<test-key>:<test-key>").decode()
    assert exporter._headers["Authorization"] == f"Basic {expected}"
    assert exporter._endpoint.endswith("/api/public/otel/v1/traces")


def test_langfuse_without_keys_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    with pytest.raises(ConfigError):
        exporter_for("langfuse", settings(tracing=["langfuse"]))


def test_cloudwatch_exporter_targets_the_regional_xray_endpoint() -> None:
    exporter = exporter_for("cloudwatch", settings(tracing=["cloudwatch"]))
    assert exporter._endpoint == "https://xray.ca-central-1.amazonaws.com/v1/traces"
    assert isinstance(exporter._session, SigV4Session)
```

Et, dans `tests/test_pipeline.py`, un test de vie privée :

```python
async def test_spans_never_carry_the_question_or_the_visitor(make_deps, spans) -> None:
    question = "Quelle expérience en MLOps chez Acme ?"
    await run_pipeline(question, "fake:echo", "visiteur-3f2a", make_deps(), lambda e: None)
    values = [str(v) for s in spans.get_finished_spans() for v in (s.attributes or {}).values()]
    assert values and not any(question in v or "visiteur-3f2a" in v for v in values)
```

(Les attributs privés `_headers`, `_endpoint`, `_session` sont ceux d'`OTLPSpanExporter` ; si leur nom diffère dans la version installée, lire le code de l'exportateur et adapter le test, sans changer l'intention.)

- [ ] **Step 2 : `src/ask_my_cv/aws/sigv4.py`**

```python
from __future__ import annotations

from typing import Any

import botocore.session
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials


class SigV4Session(requests.Session):
    """Session requests qui signe chaque requête en SigV4 (OTLP vers CloudWatch / X-Ray)."""

    def __init__(self, region: str, service: str, credentials: Credentials | None = None) -> None:
        super().__init__()
        self.region = region
        self.service = service
        self._credentials = credentials or botocore.session.Session().get_credentials()

    def request(self, method: str | bytes, url: str | bytes, *args: Any, **kwargs: Any) -> requests.Response:
        headers = {**self.headers, **(kwargs.pop("headers", None) or {})}
        data = kwargs.pop("data", None)
        aws = AWSRequest(method=str(method), url=str(url), data=data, headers=headers)
        SigV4Auth(self._credentials.get_frozen_credentials(), self.service, self.region).add_auth(aws)
        return super().request(method, url, *args, data=data, headers=dict(aws.headers.items()), **kwargs)
```

  (Si pyright proteste sur la signature surchargée de `request`, garder ce comportement et ajuster les annotations ; pas de `type: ignore` large.)
- [ ] **Step 3 : `src/ask_my_cv/telemetry.py`**

```python
from __future__ import annotations

import base64
import os
from collections.abc import Callable

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter

from ask_my_cv.settings import ConfigError, Settings


def exporter_for(name: str, settings: Settings) -> SpanExporter:
    if name == "console":
        return ConsoleSpanExporter()
    if name == "cloudwatch":
        from ask_my_cv.aws.sigv4 import SigV4Session

        return OTLPSpanExporter(
            endpoint=f"https://xray.{settings.aws_region}.amazonaws.com/v1/traces",
            session=SigV4Session(settings.aws_region, "xray"),
        )
    if name == "langfuse":
        public, secret = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
        if not public or not secret:
            raise ConfigError("tracing langfuse : LANGFUSE_PUBLIC_KEY et LANGFUSE_SECRET_KEY sont requis")
        token = base64.b64encode(f"{public}:{secret}".encode()).decode()
        return OTLPSpanExporter(
            endpoint=settings.langfuse_endpoint,
            headers={"Authorization": f"Basic {token}", "x-langfuse-ingestion-version": "4"},
        )
    raise ConfigError(f"exportateur de traces inconnu : {name}")


def build_tracer_provider(settings: Settings) -> TracerProvider | None:
    if not settings.tracing:
        return None
    provider = TracerProvider(
        resource=Resource.create({"service.name": "ask-my-cv", "deployment.environment": settings.environment})
    )
    for name in settings.tracing:
        provider.add_span_processor(BatchSpanProcessor(exporter_for(name, settings)))
    return provider


def configure_tracing(settings: Settings) -> Callable[[], None]:
    """Installe le fournisseur de traces global ; renvoie la fonction de vidage à appeler en fin de requête."""
    provider = build_tracer_provider(settings)
    if provider is None:
        return lambda: None
    trace.set_tracer_provider(provider)
    return lambda: provider.force_flush(timeout_millis=2000) and None
```

- [ ] **Step 4** — vérifier, commit : `feat: traces OpenTelemetry vers CloudWatch (SigV4) et Langfuse`.

---

### Task 6 : fabriques AWS et vidage des traces par requête

**Files:** Modify `src/ask_my_cv/container.py`, `src/ask_my_cv/app.py` ; Test `tests/test_container.py`, `tests/test_app.py`

- [ ] **Step 1 : tests**

`tests/test_container.py` :

```python
from ask_my_cv.aws.bedrock import BedrockEmbedder, BedrockLLM
from ask_my_cv.aws.dynamo import DynamoLedger, DynamoVectorStore
from ask_my_cv.container import build_embedder, build_ledger, build_provider, build_store
from ask_my_cv.settings import ModelConfig, Settings


def aws_settings() -> Settings:
    return Settings(
        models=[ModelConfig(id="bedrock:h", provider="bedrock", model="us.anthropic.claude-haiku-4-5-20251001-v1:0")],
        default_model="bedrock:h", fallback_chain=["bedrock:h"],
        embedder="bedrock", embed_dim=1024, vector_store="dynamodb", ledger="dynamodb",
    )


def test_aws_settings_build_aws_adapters_without_network() -> None:
    s = aws_settings()
    assert isinstance(build_provider(s.models[0], s), BedrockLLM)
    assert isinstance(build_embedder(s), BedrockEmbedder)
    assert isinstance(build_store(s), DynamoVectorStore)
    assert isinstance(build_ledger(s), DynamoLedger)
```

`tests/test_app.py` :

```python
async def test_traces_are_flushed_once_per_request(make_deps) -> None:
    calls: list[int] = []
    app = create_app(make_deps(), flush=lambda: calls.append(1))
    async with client_for(app) as client:
        await client.post("/ask", json={"question": "Quelle expérience ?"})
    assert calls == [1]
```

- [ ] **Step 2 : `container.py`**

```python
def aws_client(service: str, settings: Settings) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        service,
        region_name=settings.aws_region,
        config=Config(retries={"mode": "standard", "max_attempts": 3}, connect_timeout=3, read_timeout=30),
    )
```

  - `build_embedder` : `bedrock` → `BedrockEmbedder(settings.embed_model, aws_client("bedrock-runtime", settings), dim=settings.embed_dim)`.
  - `build_provider` : `bedrock` → `BedrockLLM(id=model.id, model_id=model.model, client=aws_client("bedrock-runtime", settings), pricing=pricing)`.
  - nouvelles `build_store(settings)` (file → `InMemoryVectorStore.load`, dynamodb → `DynamoVectorStore(settings.chunks_table, aws_client("dynamodb", settings))`) et `build_ledger(settings)` (memory → `InMemoryLedger(...)`, dynamodb → `DynamoLedger(settings.ledger_table, aws_client("dynamodb", settings), …)`), utilisées par `build_deps`.
  - imports AWS paresseux (dans les branches) : le mode local n'importe ni boto3 ni les adaptateurs.
- [ ] **Step 3 : `app.py`** — `create_app(deps=None, flush=None)` : si `deps is None`, charger les réglages, `flush = configure_tracing(settings)` **avant** `build_deps` ; sinon `flush = flush or (lambda: None)`. Dans `produce()`, `finally:` → `await asyncio.to_thread(flush)` puis `queue.put_nowait(None)` (les traces partent avant la fin de la réponse : une Lambda peut être gelée juste après).
- [ ] **Step 4** — vérifier, commit : `feat: fabriques AWS et vidage des traces en fin de requête`.

---

### Task 7 : documentation et suivi (contrôleur)

- [ ] README : section « Production (AWS) » : `settings.aws.yaml`, variables `VISITOR_SALT`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `ASK_SETTINGS=settings.aws.yaml`, `python -m ask_my_cv.ingest --target dynamodb`, rappel « requêtes Claude traitées aux États-Unis, embeddings au Canada ».
- [ ] `followups.md` : barrer « Exporter les traces », « Budget atomique », « Registre distant qui échoue », « Nettoyage du fournisseur Bedrock » ; ajouter pour 1c-2 : tables DynamoDB (`ask-my-cv-chunks` avec `VectorIndexes` 1024 / `DOT_PRODUCT`, `ask-my-cv-ledger` avec TTL `expires_at`), activation de Transaction Search (X-Ray OTLP), permissions IAM minimales (`bedrock:InvokeModel*` sur le profil `us.` et Titan, `dynamodb:SearchVectors/GetItem/PutItem/UpdateItem`, `xray:PutTraceSegments`/OTLP), secrets Langfuse et sel dans SSM ; vérification réelle de l'export CloudWatch (non testable sans compte).

## Critères de fin

- Tous les tests verts sans aucun appel réseau ; le mode local (`settings.yaml`) fonctionne comme avant.
- `settings.aws.yaml` se charge ; les fabriques produisent les adaptateurs AWS sans réseau.
- Les spans ne contiennent ni la question ni l'identifiant du visiteur ; Langfuse sans clés fait échouer le démarrage.
