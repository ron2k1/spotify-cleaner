import { useEffect, useRef, useState } from "react";

import { streamJob } from "@/lib/api";
import type { ErrorEvent, PhaseEvent, ProgressEvent } from "@/lib/types";

/** Subscribe to a job's SSE stream for as long as `jobId` is set, exposing the
 *  latest phase/progress and an accumulating log. Terminal callbacks live in
 *  refs so changing them never re-opens the socket. */
export function useJobStream(
  kind: "scan" | "apply",
  jobId: string | null,
  onDone: (data: unknown) => void,
  onError: (data: ErrorEvent) => void,
) {
  const [phase, setPhase] = useState<PhaseEvent | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [log, setLog] = useState<string[]>([]);

  const doneRef = useRef(onDone);
  const errorRef = useRef(onError);
  doneRef.current = onDone;
  errorRef.current = onError;

  useEffect(() => {
    setPhase(null);
    setProgress(null);
    setLog([]);
    if (!jobId) return;

    const dispose = streamJob(kind, jobId, {
      onPhase: (d) => {
        setPhase(d);
        setProgress(null);
      },
      onProgress: (d) => setProgress(d),
      onLog: (d) => setLog((prev) => [...prev, d.message]),
      onDone: (d) => doneRef.current(d),
      onError: (d) => errorRef.current(d),
    });
    return dispose;
  }, [kind, jobId]);

  return { phase, progress, log };
}
