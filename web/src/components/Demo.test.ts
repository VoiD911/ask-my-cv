import { describe as suite, expect, it } from "vitest";

import { exchangesReducer } from "./Demo";

suite("exchangesReducer", () => {
  it("applique les événements au seul échange visé puis le termine", () => {
    let state = exchangesReducer([], { type: "start", id: 1, question: "a" });
    state = exchangesReducer(state, { type: "start", id: 2, question: "b" });
    state = exchangesReducer(state, { type: "event", id: 2, event: { type: "answer", text: "ok [1]" } });
    expect(state[0]?.run.answer).toBeNull();
    expect(state[1]?.run.answer).toBe("ok [1]");
    state = exchangesReducer(state, { type: "finish", id: 2, status: "done" });
    expect(state[1]?.status).toBe("done");
    // Un échange déjà terminé ne change plus de statut.
    state = exchangesReducer(state, { type: "finish", id: 2, status: "stopped" });
    expect(state[1]?.status).toBe("done");
  });
});
