import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";

import { api } from "../../api/client";
import { Credit } from "../../design/Credit";
import { Logo } from "../../design/Logo";
import { PageHeader } from "../../design/ui";

type About = { name: string; version: string; build: string; build_date: string; django: string; python: string };

const GITHUB = "https://github.com/TheShadowConn";

export function AboutPage() {
  const q = useQuery({ queryKey: ["about"], queryFn: () => api<About>("GET", "/about"), staleTime: Infinity });
  const a = q.data;
  return (
    <>
      <PageHeader title="About" lead="Version, build and who made RedShadow." />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card card-pad" aria-labelledby="about-app-h">
          <Logo height={34} className="mb-6 text-ink" />
          <h2 id="about-app-h" className="sr-only">Application</h2>
          <p className="m-0 mb-5 text-muted">Pentest management platform: engagements, findings, evidence, remediation, audit and reporting in one self-hosted application.</p>
          {q.isError && <p role="alert" className="m-0 text-muted">Build details are not available right now.</p>}
          {a && (
            <dl className="m-0 grid gap-x-8 gap-y-3 sm:grid-cols-2">
              <div><dt className="label">Version</dt><dd className="m-0">{a.version}</dd></div>
              <div><dt className="label">Build</dt><dd className="m-0 font-mono text-[15px]">{a.build}</dd></div>
              <div><dt className="label">Build date</dt><dd className="m-0">{a.build_date || "Not recorded"}</dd></div>
              <div><dt className="label">Runtime</dt><dd className="m-0">Python {a.python}, Django {a.django}</dd></div>
            </dl>
          )}
        </section>

        <section className="card card-pad" aria-labelledby="about-maker-h">
          <h2 id="about-maker-h" className="mb-5 text-xl">Creator</h2>
          <div className="mb-5 text-ink"><Credit size="lg" /></div>
          <p className="m-0 mb-5 text-muted">Designed and built by Shadowconn.</p>
          <a href={GITHUB} target="_blank" rel="noopener noreferrer" className="btn btn-secondary inline-flex items-center gap-2">
            GitHub: TheShadowConn <ExternalLink size={16} aria-hidden />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </section>
      </div>
    </>
  );
}
