import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

import type { IntelBriefV1 } from "../types/iic";
import { formatTimestamp } from "../lib/format";
import { Card } from "./ui/Card";

export function BriefCard({ brief }: { brief: IntelBriefV1 | null | undefined }) {
  if (!brief) {
    return (
      <Card title="Today's brief">
        <p className="text-sm text-zinc-500">
          No brief yet — agents are awaiting the next digest.
        </p>
      </Card>
    );
  }
  return (
    <Card title={`Today's brief · ${formatTimestamp(brief.issued_at)}`}>
      <article className="prose prose-invert prose-sm max-w-none">
        <ReactMarkdown rehypePlugins={[rehypeSanitize]}>{brief.markdown}</ReactMarkdown>
      </article>
    </Card>
  );
}
