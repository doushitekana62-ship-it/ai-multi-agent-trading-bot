import { Container, getContainer } from "@cloudflare/containers";
import { WorkerEntrypoint } from "cloudflare:workers";

export class AiEngineContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "2m";
  enableInternet = true;
  pingEndpoint = "health";

  override async onStart() {
    console.log("AI engine container started");
  }

  override onStop({ exitCode, reason }: { exitCode: number; reason: string }) {
    console.log("AI engine container stopped", { exitCode, reason });
  }

  override onError(error: unknown) {
    console.error("AI engine container error", error);
    throw error;
  }
}

/**
 * Internal RPC facade used by the dashboard Worker.
 * The heavy CPython/NumPy/Pandas/SciPy stack stays inside the Container.
 */
export class AiEngineService extends WorkerEntrypoint {
  async analyze(payload: Record<string, unknown>) {
    const response = await getContainer(
      this.env.AI_ENGINE as DurableObjectNamespace,
      "paper-trading-ai",
    ).fetch(
      new Request("https://ai-engine.internal/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload ?? {}),
      }),
    );

    const data = (await response.json()) as Record<string, unknown>;
    if (!response.ok || data.ok !== true) {
      throw new Error(
        String(data.error ?? data.detail ?? `AI engine HTTP ${response.status}`),
      );
    }
    return data;
  }

  async health() {
    const response = await getContainer(
      this.env.AI_ENGINE as DurableObjectNamespace,
      "paper-trading-ai",
    ).fetch(new Request("https://ai-engine.internal/health"));
    return (await response.json()) as Record<string, unknown>;
  }
}

export default {
  async fetch(request: Request, env: { AI_ENGINE: DurableObjectNamespace }) {
    return getContainer(env.AI_ENGINE, "paper-trading-ai").fetch(request);
  },
};
