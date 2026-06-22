import { type ReactNode, useState } from "react";
import { Clock, Database, ListMusic, Search } from "lucide-react";

import { GdprDropzone } from "@/components/GdprDropzone";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Source, TimeRange } from "@/lib/types";

/** Everything the scan needs except `profile`, which App injects. */
export interface ScanFormValues {
  source: Source;
  min_plays: number;
  stale_days: number | null;
  time_range: TimeRange;
  top_n: number;
  min_ms: number;
  gdpr_token: string | null;
}

interface ScanFormProps {
  disabled: boolean;
  scanning: boolean;
  onScan: (values: ScanFormValues) => void;
}

function Labeled({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

export function ScanForm({
  disabled,
  scanning,
  onScan,
}: ScanFormProps) {
  const [source, setSource] = useState<Source>("toptracks");

  // Held as strings so the fields can be cleared mid-edit.
  const [minPlays, setMinPlays] = useState("2");
  const [staleDays, setStaleDays] = useState("");
  const [topN, setTopN] = useState("50");
  const [timeRange, setTimeRange] = useState<TimeRange>("long_term");
  const [minSeconds, setMinSeconds] = useState("30");
  const [gdprToken, setGdprToken] = useState<string | null>(null);

  const needsUpload = source === "gdpr" && !gdprToken;
  const canScan = !disabled && !scanning && !needsUpload;

  function submit() {
    onScan({
      source,
      min_plays: Math.max(0, Number(minPlays) || 0),
      stale_days: staleDays.trim() ? Math.max(1, Number(staleDays) || 1) : null,
      time_range: timeRange,
      top_n: Math.min(50, Math.max(1, Number(topN) || 50)),
      min_ms: Math.max(0, Math.round((Number(minSeconds) || 0) * 1000)),
      gdpr_token: gdprToken,
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scan your library</CardTitle>
        <CardDescription>
          Spotify hides play counts, so pick how to measure listening. The
          library itself (Liked Songs + your playlists) always comes from
          Spotify; the source only changes how tracks are scored.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        <ToggleGroup
          type="single"
          value={source}
          onValueChange={(v) => v && setSource(v as Source)}
          className="w-full"
        >
          <ToggleGroupItem value="toptracks">
            <ListMusic />
            Top Tracks
          </ToggleGroupItem>
          <ToggleGroupItem value="gdpr">
            <Database />
            GDPR export
          </ToggleGroupItem>
        </ToggleGroup>

        {source === "toptracks" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Labeled
              label="Time range"
              hint="Which listening window Spotify's top-tracks reflect."
            >
              <ToggleGroup
                type="single"
                value={timeRange}
                onValueChange={(v) => v && setTimeRange(v as TimeRange)}
                className="w-full"
              >
                <ToggleGroupItem value="short_term">~4 wks</ToggleGroupItem>
                <ToggleGroupItem value="medium_term">~6 mo</ToggleGroupItem>
                <ToggleGroupItem value="long_term">Years</ToggleGroupItem>
              </ToggleGroup>
            </Labeled>
            <Labeled
              label="Top N"
              hint="Flag tracks that aren't in your top N."
            >
              <Input
                type="number"
                min={1}
                max={50}
                value={topN}
                onChange={(e) => setTopN(e.target.value)}
              />
            </Labeled>
          </div>
        )}

        {source === "gdpr" && (
          <div className="space-y-4">
            <GdprDropzone
              token={gdprToken}
              onUploaded={(t) => setGdprToken(t)}
            />
            <div className="grid gap-4 sm:grid-cols-3">
              <Labeled
                label="Min seconds"
                hint="Plays shorter than this don't count."
              >
                <Input
                  type="number"
                  min={0}
                  value={minSeconds}
                  onChange={(e) => setMinSeconds(e.target.value)}
                />
              </Labeled>
              <Labeled label="Fewer than … plays" hint="The cutoff to flag.">
                <Input
                  type="number"
                  min={0}
                  value={minPlays}
                  onChange={(e) => setMinPlays(e.target.value)}
                />
              </Labeled>
              <Labeled
                label="Not played in … days"
                hint="Optional staleness cutoff."
              >
                <Input
                  type="number"
                  min={1}
                  placeholder="off"
                  value={staleDays}
                  onChange={(e) => setStaleDays(e.target.value)}
                />
              </Labeled>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <Button onClick={submit} disabled={!canScan}>
            {scanning ? (
              <Clock className="animate-spin" />
            ) : (
              <Search />
            )}
            {scanning ? "Scanning…" : "Scan library"}
          </Button>
          {needsUpload && (
            <span className="text-xs text-muted-foreground">
              Upload your GDPR export first.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
