/**
 * Client pour `GET /api/models`.
 */

export interface ModelInfo {
  readonly id: string;
  readonly provider: string;
}

export interface ModelsResponse {
  readonly default: string;
  readonly models: readonly ModelInfo[];
}

export interface FetchModelsOptions {
  readonly baseUrl?: string;
  readonly signal?: AbortSignal;
}

function isModelInfo(value: unknown): value is ModelInfo {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return typeof record["id"] === "string" && typeof record["provider"] === "string";
}

function isModelsResponse(value: unknown): value is ModelsResponse {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record["default"] === "string" &&
    Array.isArray(record["models"]) &&
    record["models"].every(isModelInfo)
  );
}

export async function fetchModels(options: FetchModelsOptions = {}): Promise<ModelsResponse> {
  const { baseUrl = "/api", signal } = options;

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/models`, { method: "GET", signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("modèles indisponibles (réseau)");
  }

  if (!response.ok) {
    throw new Error(`modèles indisponibles (${response.status})`);
  }

  const payload: unknown = await response.json();
  if (!isModelsResponse(payload)) {
    throw new Error("réponse /models mal formée");
  }
  return payload;
}
