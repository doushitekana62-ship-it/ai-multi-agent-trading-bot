import { Container, getContainer } from "@cloudflare/containers";

export class AiEngineContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "2m";
  instanceType = "standard-1";
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

export default {
  async fetch(request: Request, env: { AI_ENGINE: DurableObjectNamespace }) {
    return getContainer(env.AI_ENGINE, "paper-trading-ai").fetch(request);
  },
};
