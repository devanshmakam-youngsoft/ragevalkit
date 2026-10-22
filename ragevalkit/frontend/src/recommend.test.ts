// Run with: node --test src/recommend.test.ts   (Node 22+ strips types natively; excluded from tsc)
import assert from "node:assert/strict";
import { test } from "node:test";
import { recommend } from "./recommend.ts";

const v = (version: number, answer: number, material: number, time: number, extra: object = {}) => ({
  version, date: "", duration_seconds: 0, dataset: "d", total_rows: 8, failed_rows: 0,
  avg_answer_marks: answer, avg_material_marks: material, avg_total_time: time,
  avg_keyword_recall: null, avg_bm25_score: null, avg_semantic_similarity: null, comment: "", nodes: [], ...extra,
}) as never;

const S = { tolerance: 0.25, maxTime: null };

test("quality beats speed", () => {
  const r = recommend([v(1, 8, 8, 1.0), v(2, 9.3, 10, 2.0)], S);
  assert.equal(r.best!.version, 2);
  assert.equal(r.fastest!.version, 1);
});

test("speed breaks a near-tie", () => {
  const r = recommend([v(1, 9.3, 10, 2.0), v(2, 9.2, 10, 1.2)], S);
  assert.equal(r.best!.version, 2);
});

test("high answer but low material loses to balanced", () => {
  const r = recommend([v(1, 9.5, 5, 0.8), v(2, 9.0, 9.5, 1.6)], S);
  assert.equal(r.best!.version, 2);
});

test("time budget filters, and reports when nothing fits", () => {
  assert.equal(recommend([v(1, 8, 8, 1.0), v(2, 9.3, 10, 2.0)], { ...S, maxTime: 1.5 }).best!.version, 1);
  const none = recommend([v(1, 8, 8, 1.0)], { ...S, maxTime: 0.5 });
  assert.equal(none.best, null);
  assert.equal(none.budgetMiss, true);
});

test("failed rows and other question sets are excluded", () => {
  const r = recommend([v(1, 9.9, 10, 1, { failed_rows: 2 }), v(2, 9.0, 9, 1, { total_rows: 100 }), v(3, 8, 8, 1), v(4, 7, 7, 1)], S);
  assert.equal(r.best!.version, 3);
  assert.equal(r.excluded.length, 1);
  assert.equal(r.notComparable.length, 1);
});

test("flags a latest version that regressed", () => {
  const r = recommend([v(1, 9.5, 10, 1.2), v(2, 7, 7, 1.0)], S);
  assert.equal(r.best!.version, 1);
  assert.equal(r.latestGap!.version, 2);
});
