// Mirrors the FastAPI contracts in src/spotify_cleaner/web/{schemas,serialize}.py.
// Kept hand-written (no codegen) because the surface is small and stable.

export interface ConfigInfo {
  configured: boolean;
  redirect_uri: string;
}

export interface AuthStatus {
  profile: string;
  connected: boolean;
  display_name?: string | null;
  error?: string | null;
}

export interface ProfileInfo {
  id: string;
  connected: boolean;
}

export type Source = "toptracks" | "gdpr";
export type TimeRange = "short_term" | "medium_term" | "long_term";

export interface ScanRequest {
  source: Source;
  profile: string;
  all_tracks: boolean;
  min_plays: number;
  stale_days?: number | null;
  time_range: TimeRange;
  top_n: number;
  min_ms: number;
  gdpr_token?: string | null;
}

/** One cleanup candidate, flat — exactly what serialize.track_row emits. */
export interface TrackRow {
  track_id: string;
  uri: string;
  name: string;
  artists: string[];
  artist_label: string;
  reason: string;
  play_count: number | null;
  last_played: string | null;
  in_top: boolean | null;
  rank: number | null;
  note: string | null;
  /** How much to trust the verdict: "high" | "medium" | "low" (per source). */
  confidence: string;
  is_liked: boolean;
  playlist_ids: string[];
  playlist_count: number;
  added_at: string | null;
  /** Same-origin lazy art proxy (/api/art/{id}); 404s fall back to a placeholder. */
  album_art_url: string;
}

export interface ScanResult {
  count: number;
  source: string;
  mode: string;
  rows: TrackRow[];
}

export interface ApplyRequest {
  scan_job_id: string;
  profile: string;
  track_ids: string[];
  unlike: boolean;
  remove_from_playlists: boolean;
  confirm: string;
}

export interface JobStarted {
  job_id: string;
}

export interface GdprUploadResult {
  gdpr_token: string;
  file_count: number;
}

// --- SSE event payloads (event name -> data shape) ---

export interface PhaseEvent {
  phase: string;
  message: string;
}

export interface ProgressEvent {
  phase: string;
  current: number;
  total: number | null;
}

export interface LogEvent {
  message: string;
}

export interface ScanDoneEvent {
  count: number;
}

export interface ApplyDoneEvent {
  unliked: number;
  removed_from_playlists: number;
  playlists_touched: number;
  /** False when the pre-delete restore manifest could not be written (e.g. an
   *  unwritable backups/ dir). Absent when nothing was removed. */
  backup_written?: boolean;
}

export interface ErrorEvent {
  error: string;
}
