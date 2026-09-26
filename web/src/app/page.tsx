import { Circuit } from "@/components/Circuit";
import { createInitialState } from "@/lib/pipeline";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Interroge mon CV</h1>
      <p className="text-silk-dim">Posez une question sur le parcours de Steve Lang.</p>
      <Circuit state={createInitialState()} />
    </main>
  );
}
