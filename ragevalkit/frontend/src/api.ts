import { apiPath } from "./base";
import type { Dataset, DatasetInfo, Group, RunState, TestCase, VersionDetail, VersionSummary } from "./types";

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
  // Groups
  groups: () => fetch(apiPath("groups")).then((r) => json<Group[]>(r)),
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
  addToGroup: (groupId: string, tcId: string) =>
    fetch(apiPath(`groups/${groupId}/members/${tcId}`), { method: "POST" }).then((r) => json<object>(r)),
  removeFromGroup: (groupId: string, tcId: string) =>
    fetch(apiPath(`groups/${groupId}/members/${tcId}`), { method: "DELETE" }).then((r) => json<object>(r)),
  deleteGroup: (groupId: string) =>
    fetch(apiPath(`groups/${groupId}`), { method: "DELETE" }).then((r) => json<object>(r)),
  startRunFromGroup: (version: string, groupId: string, overwrite: boolean, statusFilter = "active") => {
    const fd = new FormData();
    fd.append("version", version);
    fd.append("overwrite", String(overwrite));
    fd.append("group_id", groupId);
    fd.append("status_filter", statusFilter);
    return fetch(apiPath("runs"), { method: "POST", body: fd }).then((r) => json<RunState>(r));
  },
  startRunFromGroups: (version: string, groupIds: string[], overwrite: boolean, statusFilter = "active", notes = "") => {
    const fd = new FormData();
    fd.append("version", version);
    fd.append("overwrite", String(overwrite));
    fd.append("group_ids", JSON.stringify(groupIds));
    fd.append("status_filter", statusFilter);
    fd.append("notes", notes);
    return fetch(apiPath("runs"), { method: "POST", body: fd }).then((r) => json<RunState>(r));
  },
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
  editTestCase: (tcId: string, updates: Partial<Pick<TestCase, "question" | "expected_answer" | "expected_sources" | "type">>) =>
    fetch(apiPath(`test-cases/${tcId}`), {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates),
    }).then((r) => json<TestCase>(r)),
  updateTestCaseStatus: (tcId: string, status: "active" | "inactive" | "deleted") =>
    fetch(apiPath(`test-cases/${tcId}/status`), {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
    }).then((r) => json<{ tc_id: string; status: string }>(r)),
  uploadDataset: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(apiPath("datasets/upload"), { method: "POST", body: fd }).then((r) => json<{ dataset_id: string; rows: number }>(r));
  },
  createTestCase: (body: { chat_id: string; turn_no: number; question: string; expected_answer: string; type?: string; expected_sources?: string; group_id?: string }) =>
    fetch(apiPath("test-cases"), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }).then((r) => json<TestCase>(r)),
  startRunFromLibrary: (version: string, datasetId: string, overwrite: boolean, statusFilter = "active") => {
    const fd = new FormData();
    fd.append("version", version);
    fd.append("overwrite", String(overwrite));
    fd.append("group_id", datasetId); // was dataset_id, now maps to group_id
    fd.append("status_filter", statusFilter);
    return fetch(apiPath("runs"), { method: "POST", body: fd }).then((r) => json<RunState>(r));
  },
};
