import { apiPath } from "./base";
import type { DatasetInfo, Group, GroupHistory, ImportMapping, ImportPreview, ImportResult, RecoResult, RunPreview, RunSelection, RunState, TestCase, VersionDetail, VersionSummary } from "./types";

/** Fired when any call comes back 401 so the app can return to the login page. */
export const authEvents = new EventTarget();

async function json<T>(res: Response, { notifyUnauthorized = true } = {}): Promise<T> {
  if (!res.ok) {
    if (res.status === 401 && notifyUnauthorized) authEvents.dispatchEvent(new Event("unauthorized"));
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export const api = {
  login: (username: string, password: string) =>
    fetch(apiPath("auth/login"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }),
    }).then((r) => json<{ username: string }>(r, { notifyUnauthorized: false })),
  logout: () => fetch(apiPath("auth/logout"), { method: "POST" }).then(() => undefined),
  me: () => fetch(apiPath("auth/me")).then((r) => json<{ username: string }>(r, { notifyUnauthorized: false })),
  versions: () => fetch(apiPath("versions")).then((r) => json<VersionSummary[]>(r)),
  version: (v: string) => fetch(apiPath(`versions/${encodeURIComponent(v)}`)).then((r) => json<VersionDetail>(r)),
  runs: () => fetch(apiPath("runs")).then((r) => json<RunState[]>(r)),
  defaultDataset: () => fetch(apiPath("dataset/default")).then((r) => json<DatasetInfo>(r)),
  validateDataset: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(apiPath("dataset/validate"), { method: "POST", body: fd }).then((r) => json<DatasetInfo>(r));
  },
  startRun: (version: string, file: File | null, overwrite: boolean) => {
    const fd = new FormData();
    fd.append("version", version);
    fd.append("overwrite", String(overwrite));
    if (file) fd.append("file", file);
    return fetch(apiPath("runs"), { method: "POST", body: fd }).then((r) => json<RunState>(r));
  },
  downloadUrl: (v: string) => apiPath(`versions/${encodeURIComponent(v)}/download`),
  stopRun: (runId: string) =>
    fetch(apiPath(`runs/${runId}/stop`), { method: "POST" }).then((r) => json<{ run_id: string; message: string }>(r)),
  archiveRun: (runId: string) =>
    fetch(apiPath(`runs/${runId}/archive`), { method: "PATCH" }).then((r) => json(r)),
  unarchiveRun: (runId: string) =>
    fetch(apiPath(`runs/${runId}/unarchive`), { method: "PATCH" }).then((r) => json(r)),
  deleteRun: (runId: string) =>
    fetch(apiPath(`runs/${runId}`), { method: "DELETE" }).then((r) => json(r)),
  /** Which version to ship, computed by the server from non-archived runs. Omit overrides to use serve() defaults. */
  recommendation: (o: { group?: string | null; tolerance?: number | null; maxTime?: number | null } = {}) => {
    const params = new URLSearchParams();
    if (o.group) params.set("group", o.group);
    if (o.tolerance != null) params.set("tolerance", String(o.tolerance));
    if (o.maxTime != null) params.set("max_time", String(o.maxTime));
    const qs = params.toString();
    return fetch(apiPath(`recommendation${qs ? `?${qs}` : ""}`)).then((r) => json<RecoResult>(r));
  },
  // Groups
  groupHistory: (groupId: string) => fetch(apiPath(`groups/${groupId}/runs`)).then((r) => json<GroupHistory>(r)),
  groups: (includeDeleted = false) =>
    fetch(apiPath(`groups${includeDeleted ? "?include_deleted=true" : ""}`)).then((r) => json<Group[]>(r)),
  restoreGroup: (groupId: string) =>
    fetch(apiPath(`groups/${groupId}/restore`), { method: "POST" }).then((r) => json<object>(r)),
  purgeGroup: (groupId: string) =>
    fetch(apiPath(`groups/${groupId}/purge`), { method: "POST" }).then((r) => json<object>(r)),
  createGroup: (name: string) =>
    fetch(apiPath("groups"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) })
      .then((r) => json<Group>(r)),
  importIntoGroup: (groupId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(apiPath(`groups/${groupId}/import`), { method: "POST", body: fd })
      .then((r) => json<{ group_id: string; linked: number }>(r));
  },
  groupTestCases: (groupId: string, status?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    const qs = params.toString();
    return fetch(apiPath(`groups/${groupId}/test-cases${qs ? `?${qs}` : ""}`)).then((r) => json<TestCase[]>(r));
  },
  renameGroup: (groupId: string, name: string) =>
    fetch(apiPath(`groups/${groupId}`), {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
    }).then((r) => json<Group>(r)),
  addToGroup: (groupId: string, tcIds: string[]) =>
    fetch(apiPath(`groups/${groupId}/members`), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tc_ids: tcIds }),
    }).then((r) => json<{ added: number }>(r)),
  removeFromGroup: (groupId: string, tcIds: string[]) =>
    fetch(apiPath(`groups/${groupId}/members/remove`), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tc_ids: tcIds }),
    }).then((r) => json<{ removed: number }>(r)),
  setTestCaseGroups: (tcId: string, groupIds: string[]) =>
    fetch(apiPath(`test-cases/${tcId}/groups`), {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ group_ids: groupIds }),
    }).then((r) => json<object>(r)),
  deleteGroup: (groupId: string) =>
    fetch(apiPath(`groups/${groupId}`), { method: "DELETE" }).then((r) => json<object>(r)),
  /** Start a run from the library: any mix of groups and individually picked test cases. */
  startRunFromSelection: (version: string, overwrite: boolean, notes: string, sel: RunSelection) => {
    const fd = new FormData();
    fd.append("version", version);
    fd.append("overwrite", String(overwrite));
    fd.append("group_ids", JSON.stringify(sel.groupIds ?? []));
    fd.append("tc_ids", JSON.stringify(sel.tcIds ?? []));
    fd.append("status_filter", sel.statusFilter ?? "active");
    fd.append("include_context", String(sel.includeContext ?? true));
    fd.append("notes", notes);
    return fetch(apiPath("runs"), { method: "POST", body: fd }).then((r) => json<RunState>(r));
  },
  /** Dry run: how many test cases a selection would execute. */
  previewRun: (sel: RunSelection) =>
    fetch(apiPath("runs/preview"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        group_ids: sel.groupIds ?? [], tc_ids: sel.tcIds ?? [],
        status_filter: sel.statusFilter ?? "active", include_context: sel.includeContext ?? true,
      }),
    }).then((r) => json<RunPreview>(r)),
  startRunAndSave: (version: string, file: File, overwrite: boolean, groupName: string) => {
    const fd = new FormData();
    fd.append("version", version);
    fd.append("overwrite", String(overwrite));
    fd.append("file", file);
    fd.append("save_as_group", "true");
    fd.append("group_name", groupName);
    return fetch(apiPath("runs"), { method: "POST", body: fd }).then((r) => json<RunState>(r));
  },
  // Test cases
  datasets: () => fetch(apiPath("groups")).then((r) => json<Group[]>(r)), // backward-compat alias
  testCases: (groupId?: string, status?: string) => {
    const params = new URLSearchParams();
    if (groupId) params.set("group_id", groupId);
    if (status) params.set("status", status);
    const qs = params.toString();
    return fetch(apiPath(`test-cases${qs ? `?${qs}` : ""}`)).then((r) => json<TestCase[]>(r));
  },
  testCaseHistory: (tcId: string) =>
    fetch(apiPath(`test-cases/${tcId}/history`)).then((r) => json<TestCase[]>(r)),
  editTestCase: (tcId: string, updates: Partial<Pick<TestCase, "chat_id" | "turn_no" | "question" | "expected_answer" | "expected_sources" | "type">>) =>
    fetch(apiPath(`test-cases/${tcId}`), {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates),
    }).then((r) => json<TestCase>(r)),
  // Bulk import of test cases
  importTemplateUrl: () => apiPath("test-cases/import/template"),
  previewImport: (file: File, o: { sheet?: string | null; mapping?: ImportMapping | null } = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (o.sheet) fd.append("sheet", o.sheet);
    if (o.mapping) fd.append("mapping", JSON.stringify(o.mapping));
    return fetch(apiPath("test-cases/import/preview"), { method: "POST", body: fd }).then((r) => json<ImportPreview>(r));
  },
  importCases: (file: File, o: {
    sheet?: string | null; mapping?: ImportMapping | null; groupIds?: string[]; newGroupName?: string; updateBySlot?: boolean;
  } = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (o.sheet) fd.append("sheet", o.sheet);
    if (o.mapping) fd.append("mapping", JSON.stringify(o.mapping));
    fd.append("group_ids", JSON.stringify(o.groupIds ?? []));
    if (o.newGroupName) fd.append("new_group_name", o.newGroupName);
    fd.append("update_by_slot", String(o.updateBySlot ?? false));
    return fetch(apiPath("test-cases/import"), { method: "POST", body: fd }).then((r) => json<ImportResult>(r));
  },
  /** Permanently removes test cases that are already deleted. Past run results are kept. */
  purgeTestCases: (tcIds: string[]) =>
    fetch(apiPath("test-cases/purge"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tc_ids: tcIds }),
    }).then((r) => json<{ purged: number }>(r)),
  updateTestCaseStatus: (tcIds: string[], status: "active" | "inactive" | "deleted") =>
    fetch(apiPath("test-cases/status"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tc_ids: tcIds, status }),
    }).then((r) => json<{ updated: number; status: string }>(r)),
  uploadDataset: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(apiPath("datasets/upload"), { method: "POST", body: fd }).then((r) => json<{ dataset_id: string; rows: number }>(r));
  },
  createTestCase: (body: { chat_id: string; turn_no: number; question: string; expected_answer: string; type?: string; expected_sources?: string; group_id?: string }) =>
    fetch(apiPath("test-cases"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }).then((r) => json<TestCase>(r)),
};
