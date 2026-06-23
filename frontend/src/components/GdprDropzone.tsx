import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { FileJson, Loader2, Upload } from "lucide-react";
import { toast } from "sonner";

import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface GdprDropzoneProps {
  token: string | null;
  onUploaded: (token: string, fileCount: number) => void;
}

/** Drop the Spotify GDPR export (the .zip Spotify emails, or the loose
 *  Streaming_History_*.json files). The server extracts + flattens them and
 *  returns an opaque token the scan request references. */
export function GdprDropzone({ token, onUploaded }: GdprDropzoneProps) {
  const [busy, setBusy] = useState(false);
  const [count, setCount] = useState<number | null>(null);

  const onDrop = useCallback(
    async (accepted: File[]) => {
      if (accepted.length === 0) return;
      setBusy(true);
      try {
        const res = await api.uploadGdpr(accepted);
        setCount(res.file_count);
        onUploaded(res.gdpr_token, res.file_count);
        toast.success(`Loaded ${res.file_count} history file(s).`);
      } catch (e) {
        const detail = e instanceof ApiError ? e.detail : "upload_failed";
        toast.error(
          detail === "no_streaming_history_json"
            ? "No Streaming_History_*.json found in that drop."
            : `Upload failed (${detail}).`,
        );
      } finally {
        setBusy(false);
      }
    },
    [onUploaded],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/json": [".json"],
      "application/zip": [".zip"],
      "application/x-zip-compressed": [".zip"],
    },
    disabled: busy,
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-input bg-background/40 p-6 text-center transition-colors hover:border-primary/60",
        isDragActive && "border-primary bg-primary/5",
        busy && "pointer-events-none opacity-70",
      )}
    >
      <input {...getInputProps()} />
      {busy ? (
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      ) : token ? (
        <FileJson className="size-6 text-primary" />
      ) : (
        <Upload className="size-6 text-muted-foreground" />
      )}
      <div className="text-sm">
        {token ? (
          <span className="text-foreground">
            {count ?? "Some"} history file(s) loaded — drop again to replace.
          </span>
        ) : (
          <span className="text-muted-foreground">
            Drop your{" "}
            <code className="rounded bg-muted px-1">my_spotify_data.zip</code>{" "}
            or{" "}
            <code className="rounded bg-muted px-1">
              Streaming_History_*.json
            </code>{" "}
            here, or click to browse.
          </span>
        )}
      </div>
    </div>
  );
}
