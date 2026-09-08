/** uripack-owned contracts; no execution authority and no native Subactor SDK claim. */
export interface ServiceProfile {
  schema: "uripack.service-profile/v1";
  language: "python" | "node";
  base_image: string;
  workdir: string;
  command: string[];
  dependency_file: string;
  ports?: number[];
}
export interface ExtractionUnit {
  id: string;
  include: string[];
  public_uris?: string[];
  depends_on?: string[];
}
export interface RefactorRequest {
  schema: "uripack.refactor-request/v1";
  operation: "plan";
  namespace: string;
  units: ExtractionUnit[];
  checks?: string[];
  limits?: { max_files: number; max_bytes: number };
}
export interface RefactorRequestV2 extends Omit<RefactorRequest, "schema" | "units"> {
  schema: "uripack.refactor-request/v2";
  units: (ExtractionUnit & { service?: ServiceProfile })[];
}
export interface CheckResult {
  schema: "uripack.check-result/v1";
  status: "passed" | "failed" | "blocked";
  subject_sha256: string;
  artifact_sha256: string;
  evidence_refs: string[];
}
export interface GuardResponse {
  schema: "uripack.guard-response/v1";
  request_id: string;
  allowed: boolean;
  subject_sha256: string;
  decision_ref: string;
  lease_ref: string;
  fencing_token: number;
  expires_at: number;
  result?: unknown;
}

/** Matches Python uripack.c14n/v1. Not full RFC8785 and not wellmanifest/logs. */
export function canonical(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) throw new Error("UPK-DATA-001");
    return String(value);
  }
  if (typeof value === "string") {
    for (const ch of value) {
      const cp = ch.codePointAt(0)!;
      if (cp >= 0xd800 && cp <= 0xdfff) throw new Error("UPK-DATA-001");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (typeof value === "object" && value !== null &&
      [null, Object.prototype].includes(Object.getPrototypeOf(value))) {
    const v = value as Record<string, unknown>;
    return "{" + Object.keys(v).sort().map(k => canonical(k) + ":" + canonical(v[k])).join(",") + "}";
  }
  throw new Error("UPK-DATA-001");
}

function object(value: unknown, allowed: string[], required: string[]): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("UPK-CONTRACT-001");
  const obj = value as Record<string, unknown>;
  if (Object.keys(obj).some(k => !allowed.includes(k)) || required.some(k => !(k in obj))) throw new Error("UPK-CONTRACT-001");
  return obj;
}
function strings(v: unknown, min: number, max: number, check: (s: string) => boolean): void {
  if (!Array.isArray(v) || v.length < min || v.length > max || new Set(v).size !== v.length ||
      v.some(x => typeof x !== "string" || !check(x))) throw new Error("UPK-CONTRACT-001");
}
const id = (s: string): boolean => /^[a-z][a-z0-9.-]{0,95}$/.test(s);
const inRange = (v: unknown, min: number, max: number): boolean => typeof v === "number" && Number.isSafeInteger(v) && v >= min && v <= max;

/** Shape validator. Graph, filesystem, path and public-URI existence checks run in Python planner. */
export function assertRefactorRequest(value: unknown): asserts value is RefactorRequest | RefactorRequestV2 {
  canonical(value);
  const r = object(value, ["schema","operation","namespace","units","checks","limits"], ["schema","operation","namespace","units"]);
  if (typeof r.schema !== "string" || !["uripack.refactor-request/v1", "uripack.refactor-request/v2"].includes(r.schema) || r.operation !== "plan" || typeof r.namespace !== "string" || !id(r.namespace)) throw new Error("UPK-CONTRACT-001");
  if (!Array.isArray(r.units) || r.units.length < 1 || r.units.length > 100 || new Set(r.units.map(canonical)).size !== r.units.length) throw new Error("UPK-CONTRACT-001");
  for (const unit of r.units) {
    const fields = ["id","include","public_uris","depends_on"];
    if (r.schema === "uripack.refactor-request/v2") fields.push("service");
    const u = object(unit, fields, ["id","include"]);
    if ("service" in u) assertServiceProfile(u.service);
    if (typeof u.id !== "string" || !id(u.id)) throw new Error("UPK-CONTRACT-001");
    strings(u.include, 1, 256, s => [...s].length >= 1 && [...s].length <= 1024);
    if ("public_uris" in u) strings(u.public_uris, 0, 1000, s => [...s].length >= 3 && [...s].length <= 2048);
    if ("depends_on" in u) strings(u.depends_on, 0, 100, id);
  }
  if ("checks" in r) strings(r.checks, 0, 100, id);
  if ("limits" in r) {
    const l = object(r.limits, ["max_files","max_bytes"], ["max_files","max_bytes"]);
    if (!inRange(l.max_files,1,10000) || !inRange(l.max_bytes,1,134217728)) throw new Error("UPK-CONTRACT-001");
  }
}

/** Shape only; selected paths and one-process ownership are validated by the planner. */
export function assertServiceProfile(value: unknown): asserts value is ServiceProfile {
  canonical(value);
  const s = object(value, ["schema","language","base_image","workdir","command","dependency_file","ports"],
    ["schema","language","base_image","workdir","command","dependency_file"]);
  if (s.schema !== "uripack.service-profile/v1" || typeof s.language !== "string" || !["python","node"].includes(s.language)) throw new Error("UPK-CONTRACT-001");
  if (typeof s.base_image !== "string" || s.base_image.length > 512 || !/^[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}$(?![\s\S])/.test(s.base_image)) throw new Error("UPK-CONTRACT-001");
  for (const field of ["workdir","dependency_file"]) {
    const path = s[field];
    if (typeof path !== "string" || path.length > 1024 || !/^[A-Za-z0-9_./-]+$(?![\s\S])/.test(path)) throw new Error("UPK-CONTRACT-001");
  }
  if (!Array.isArray(s.command) || s.command.length < 1 || s.command.length > 64 ||
    s.command.some(arg => typeof arg !== "string" || [...arg].length < 1 || [...arg].length > 4096 || /[\x00-\x1f\x7f]/.test(arg))) throw new Error("UPK-CONTRACT-001");
  if ("ports" in s && (!Array.isArray(s.ports) || s.ports.length > 32 || new Set(s.ports).size !== s.ports.length ||
    s.ports.some(port => !inRange(port, 1, 65535)))) throw new Error("UPK-CONTRACT-001");
}
