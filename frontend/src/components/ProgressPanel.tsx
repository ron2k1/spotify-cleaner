import { Loader2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { PhaseEvent, ProgressEvent } from "@/lib/types";

interface ProgressPanelProps {
  title: string;
  phase: PhaseEvent | null;
  progress: ProgressEvent | null;
  log: string[];
}

export function ProgressPanel({
  title,
  phase,
  progress,
  log,
}: ProgressPanelProps) {
  // Determinate only when the worker knows the total; otherwise the spinner
  // alone conveys "working" (no fake bar).
  const pct =
    progress && progress.total
      ? Math.round((progress.current / progress.total) * 100)
      : null;

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Loader2 className="size-4 animate-spin text-primary" />
          {title}
        </div>

        <div className="text-sm text-muted-foreground">
          {phase?.message ?? "Starting…"}
        </div>

        {pct !== null && (
          <div className="flex items-center gap-3">
            <Progress value={pct} className="flex-1" />
            <span className="w-12 text-right text-xs tabular-nums text-muted-foreground">
              {pct}%
            </span>
          </div>
        )}

        {log.length > 0 && (
          <ul className="max-h-24 overflow-y-auto rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
            {log.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
