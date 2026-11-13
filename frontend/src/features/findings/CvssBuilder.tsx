import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { Select } from "../../design/ui";
import { SeverityBadge } from "./shared";

type Metric = { key: string; name: string; options: Array<[string, string]> };

const IMPACT: Array<[string, string]> = [["N", "None"], ["L", "Low"], ["H", "High"]];
const IMPACT_H: Array<[string, string]> = [["H", "High"], ["L", "Low"], ["N", "None"]];

const V31: Metric[] = [
  { key: "AV", name: "Attack vector", options: [["N", "Network"], ["A", "Adjacent"], ["L", "Local"], ["P", "Physical"]] },
  { key: "AC", name: "Attack complexity", options: [["L", "Low"], ["H", "High"]] },
  { key: "PR", name: "Privileges required", options: IMPACT },
  { key: "UI", name: "User interaction", options: [["N", "None"], ["R", "Required"]] },
  { key: "S", name: "Scope", options: [["U", "Unchanged"], ["C", "Changed"]] },
  { key: "C", name: "Confidentiality impact", options: IMPACT_H },
  { key: "I", name: "Integrity impact", options: IMPACT_H },
  { key: "A", name: "Availability impact", options: IMPACT_H },
];

const V40: Metric[] = [
  { key: "AV", name: "Attack vector", options: [["N", "Network"], ["A", "Adjacent"], ["L", "Local"], ["P", "Physical"]] },
  { key: "AC", name: "Attack complexity", options: [["L", "Low"], ["H", "High"]] },
  { key: "AT", name: "Attack requirements", options: [["N", "None"], ["P", "Present"]] },
  { key: "PR", name: "Privileges required", options: IMPACT },
  { key: "UI", name: "User interaction", options: [["N", "None"], ["P", "Passive"], ["A", "Active"]] },
  { key: "VC", name: "Vulnerable system confidentiality", options: IMPACT_H },
  { key: "VI", name: "Vulnerable system integrity", options: IMPACT_H },
  { key: "VA", name: "Vulnerable system availability", options: IMPACT_H },
  { key: "SC", name: "Subsequent system confidentiality", options: [["N", "None"], ["L", "Low"], ["H", "High"]] },
  { key: "SI", name: "Subsequent system integrity", options: [["N", "None"], ["L", "Low"], ["H", "High"]] },
  { key: "SA", name: "Subsequent system availability", options: [["N", "None"], ["L", "Low"], ["H", "High"]] },
];

const DEFAULTS_31: Record<string, string> = { AV: "N", AC: "L", PR: "N", UI: "N", S: "U", C: "H", I: "H", A: "H" };
const DEFAULTS_40: Record<string, string> = { AV: "N", AC: "L", AT: "N", PR: "N", UI: "N", VC: "H", VI: "H", VA: "H", SC: "N", SI: "N", SA: "N" };

type Version = "3.1" | "4.0";

function versionOf(vector: string): Version | null {
  return vector.startsWith("CVSS:3.1/") ? "3.1" : vector.startsWith("CVSS:4.0/") ? "4.0" : null;
}

function parse(vector: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of vector.split("/").slice(1)) {
    const [k, v] = part.split(":");
    if (k && v) out[k] = v;
  }
  return out;
}

function build(version: Version, values: Record<string, string>): string {
  const metrics = version === "3.1" ? V31 : V40;
  return `CVSS:${version}/` + metrics.map((m) => `${m.key}:${values[m.key]}`).join("/");
}

export function useCvssScore(vector: string) {
  const [debounced, setDebounced] = useState(vector);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(vector), 300);
    return () => clearTimeout(t);
  }, [vector]);
  return useQuery({
    queryKey: ["cvss", debounced],
    queryFn: () => api<{ version: string; score: string; severity: string }>("POST", "/findings/cvss", { vector: debounced }),
    enabled: !!debounced,
    retry: false,
  });
}

/** Builds a CVSS 3.1 or 4.0 base vector. The score is always computed by the server. */
export function CvssBuilder({ value, onChange }: { value: string; onChange: (vector: string) => void }) {
  const version = versionOf(value);
  const score = useCvssScore(value);
  const metrics = version === "3.1" ? V31 : V40;
  const values = parse(value);

  function pickVersion(v: string) {
    if (!v) return onChange("");
    onChange(build(v as Version, v === "3.1" ? DEFAULTS_31 : DEFAULTS_40));
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="field">
          <label htmlFor="cvss-version">CVSS</label>
          <Select id="cvss-version" value={version ?? (value ? "custom" : "")} onChange={(e) => pickVersion(e.target.value)}>
            <option value="">No CVSS, set severity by hand</option>
            <option value="3.1">CVSS 3.1</option>
            <option value="4.0">CVSS 4.0</option>
            {value && !version && <option value="custom" disabled>Unrecognised vector</option>}
          </Select>
        </div>
        <div className="field">
          <label htmlFor="cvss-vector">Vector</label>
          <input
            id="cvss-vector"
            className="input mono"
            value={value}
            spellCheck={false}
            placeholder="Paste a CVSS:3.1/… or CVSS:4.0/… vector"
            onChange={(e) => onChange(e.target.value.trim())}
          />
        </div>
      </div>

      {version && (
        <div className="grid gap-4 sm:grid-cols-2">
          {metrics.map((m) => (
            <div className="field" key={m.key}>
              <label htmlFor={`cvss-${m.key}`}>{m.name}</label>
              <Select id={`cvss-${m.key}`} value={values[m.key] ?? ""} onChange={(e) => onChange(build(version, { ...values, [m.key]: e.target.value }))}>
                {m.options.map(([k, name]) => (
                  <option key={k} value={k}>{name}</option>
                ))}
              </Select>
            </div>
          ))}
        </div>
      )}

      {value && (
        <p className="m-0 flex flex-wrap items-center gap-3" aria-live="polite">
          <span className="text-muted">Score</span>
          {score.isPending && <span className="text-muted">Calculating…</span>}
          {score.isError && <span className="text-fail">This is not a valid CVSS vector.</span>}
          {score.data && <SeverityBadge severity={score.data.severity} score={score.data.score} />}
          {score.data && <span className="text-[13px] text-muted">Calculated by the server</span>}
        </p>
      )}
    </div>
  );
}
