import { Link } from "react-router-dom";

import { Card } from "../components/ui/Card";

const SLUGS = ["rogers", "buffett", "soros", "druckenmiller", "wood", "dalio", "burry", "degen"];

const DISPLAY: Record<string, string> = {
  rogers: "Jim Rogers",
  buffett: "Warren Buffett",
  soros: "George Soros",
  druckenmiller: "Stanley Druckenmiller",
  wood: "Cathie Wood",
  dalio: "Ray Dalio",
  burry: "Michael Burry",
  degen: "Anonymous Retail",
};

/**
 * Workflow 13 §9 + 21 §8: avatars are stylized initials, NEVER real photos.
 */
function Initials({ slug }: { slug: string }) {
  const name = DISPLAY[slug] ?? slug;
  const initials = name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("");
  return (
    <div className="flex h-12 w-12 items-center justify-center rounded-full border border-zinc-700 bg-zinc-800 text-sm font-medium text-zinc-200">
      {initials.toUpperCase()}
    </div>
  );
}

export function Personas() {
  return (
    <Card title="Personas">
      <p className="mb-4 text-xs text-zinc-500">
        Stylized agents inspired by public writings — never the real investors. Avatars
        are initials, not likenesses.
      </p>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SLUGS.map((slug) => (
          <li key={slug}>
            <Link
              to={`/agents/persona.${slug}`}
              className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3 hover:border-zinc-700"
            >
              <Initials slug={slug} />
              <div>
                <div className="text-sm font-medium text-zinc-200">{DISPLAY[slug]}</div>
                <div className="text-xs text-zinc-500">persona.{slug}</div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
