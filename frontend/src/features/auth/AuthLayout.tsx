import type { ReactNode } from "react";
import { KeyRound, ListChecks, ScrollText } from "lucide-react";

const POINTS = [
  { icon: ListChecks, text: "Track every engagement from kick-off to verified fix." },
  { icon: KeyRound, text: "Scoped access: people only see what they are assigned." },
  { icon: ScrollText, text: "A tamper-evident record of every change." },
];

/** Decorative: the "O" of the RedShadow logo (rounded block with its diagonal cut), large and see-through. */
function OMark() {
  return (
    <svg aria-hidden viewBox="0 0 84 100" className="pointer-events-none absolute top-1/2 -right-24 z-0 h-[760px] w-auto -translate-y-1/2">
      <rect x="-14" y="-17" width="112" height="134" rx="36" fill="none" stroke="#fff" strokeWidth="0.5" opacity="0.18" />
      <rect x="0" y="0" width="84" height="100" rx="27" fill="#fff" opacity="0.13" />
      <path d="M60 32V77C60 78.1 59.1 79 58 79H26C24.89 79 24 78.1 24 77V68L60 32Z" fill="#4d0510" opacity="0.5" />
    </svg>
  );
}

/** Sign-in surface: a Racing Red brand panel beside the form, stacked on phones. */
export function AuthLayout({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-[linear-gradient(160deg,#ef233c_0%,#b10f27_58%,#4d0510_100%)] p-12 text-white lg:flex">
        <OMark />
        <img src="/brand/redshadow-eclipse-white.svg" alt="RedShadow" className="relative z-10 h-9 w-auto self-start" />
        <div className="relative z-10 max-w-md">
          <p className="m-0 text-[40px] leading-[1.1] font-semibold tracking-[-0.03em]">Offensive security, managed with discipline.</p>
          <ul className="m-0 mt-8 list-none space-y-3 p-0">
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex gap-4 rounded-[10px] bg-[rgb(20_4_8/0.34)] px-4 py-3 text-[17px] leading-snug">
                <Icon size={20} className="mt-0.5 flex-none" aria-hidden />
                {text}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative z-10 m-0 flex items-center gap-2.5 text-[13px] text-white/80">
          Built by
          <img src="/brand/shadowconn-wolf-white.svg" alt="" className="h-5 w-auto" />
          <img src="/brand/shadowconn-wordmark-white.svg" alt="Shadowconn" className="h-3 w-auto" />
        </p>
      </aside>

      <main className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-[420px]">
          <img src="/brand/redshadow-eclipse-ink.svg" alt="RedShadow" className="mb-10 h-8 w-auto lg:hidden" />
          <h1 className="text-[30px]">{title}</h1>
          {lead && <p className="mt-2 mb-8 text-muted">{lead}</p>}
          {!lead && <div className="mb-8" />}
          {children}
        </div>
      </main>
    </div>
  );
}
