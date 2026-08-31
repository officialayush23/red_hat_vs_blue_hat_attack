import { ATTACK_CATALOG, getAttackById } from "@/data/attackCatalog";
import { getCaseForAttack, getEvaluationCases } from "@/data/mockStore";
import { mockDelay } from "@/services/api/client";

// GET /api/attacks
export async function listAttacks() {
  return mockDelay(ATTACK_CATALOG);
}

// GET /api/attacks/:id
export async function getAttack(id) {
  return mockDelay(getAttackById(id));
}

// GET /api/attacks/:id/cases?limit=
export async function getAttackCases(runId, limit = 6) {
  return mockDelay(getEvaluationCases(runId, limit));
}

// GET /api/attacks/:id/representative-case
export async function getRepresentativeCase(attackId) {
  return mockDelay(getCaseForAttack(attackId));
}
