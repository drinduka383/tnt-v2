const terminal = new Set(['succeeded', 'insufficient_evidence', 'failed', 'cancelled']);
export const isTerminal = status => terminal.has(status);
const statuses = new Set(['accepted', 'running', ...terminal]);
export function validateRun(run) {
  if (!run || typeof run.id !== 'string' || !statuses.has(run.status)) throw new Error('The service returned an invalid run state.');
  return run;
}
