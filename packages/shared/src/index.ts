export type OutboxEvent =
  | { id: string; type: "probe_drop_created"; tsMs: number; payload: unknown };