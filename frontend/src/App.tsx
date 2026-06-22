import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type RowSelectionState } from "@tanstack/react-table";
import { toast } from "sonner";

import { CandidateTable } from "@/components/CandidateTable";
import { ConfirmApplyDialog } from "@/components/ConfirmApplyDialog";
import { ProfileBar } from "@/components/ProfileBar";
import { ProgressPanel } from "@/components/ProgressPanel";
import { ScanForm, type ScanFormValues } from "@/components/ScanForm";
import { SetupBanner } from "@/components/SetupBanner";
import { ApiError, api } from "@/lib/api";
import type {
  ApplyDoneEvent,
  AuthStatus,
  ConfigInfo,
  ErrorEvent,
  ProfileInfo,
  ScanResult,
} from "@/lib/types";
import { useJobStream } from "@/lib/useJobStream";

/** Turn an ApiError detail code into something a person can act on. */
function explain(e: unknown): string {
  const detail = e instanceof ApiError ? e.detail : "unexpected_error";
  switch (detail) {
    case "not_connected":
      return "Connect Spotify for this profile first.";
    case "spotify_app_not_configured":
      return "Set your Spotify Client ID/Secret, then restart the server.";
    case "gdpr_upload_missing":
      return "Re-upload your GDPR export — the previous one expired.";
    default:
      return `Something went wrong (${detail}).`;
  }
}

export default function App() {
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [profile, setProfile] = useState("default");
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authLoading, setAuthLoading] = useState(false);

  const [scanId, setScanId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const [applyId, setApplyId] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  const pendingApplyIds = useRef<string[]>([]);

  const configured = Boolean(config?.configured);

  const refreshProfiles = useCallback(() => {
    api.getProfiles().then(setProfiles).catch(() => undefined);
  }, []);

  const refreshAuth = useCallback(
    async (p: string) => {
      if (!configured) return;
      setAuthLoading(true);
      try {
        setAuth(await api.getAuthStatus(p));
      } catch (e) {
        setAuth({
          profile: p,
          connected: false,
          error: e instanceof ApiError ? e.detail : "error",
        });
      } finally {
        setAuthLoading(false);
      }
    },
    [configured],
  );

  // Initial load: config + profiles, and handle the post-OAuth redirect.
  useEffect(() => {
    api
      .getConfig()
      .then(setConfig)
      .catch(() =>
        setConfig({
          configured: false,
          redirect_uri: "",
        }),
      );
    refreshProfiles();

    const params = new URLSearchParams(window.location.search);
    const a = params.get("auth");
    if (a) {
      const p = params.get("profile");
      if (a === "ok") {
        toast.success("Connected to Spotify.");
        if (p) setProfile(p);
      } else if (a === "badstate") {
        toast.error("Login session expired — please try again.");
      } else {
        toast.error("Spotify login failed or was cancelled.");
      }
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [refreshProfiles]);

  // Debounced auth check whenever the active profile changes.
  useEffect(() => {
    if (!configured) return;
    const id = setTimeout(() => refreshAuth(profile), 300);
    return () => clearTimeout(id);
  }, [profile, configured, refreshAuth]);

  // --- Scan stream ---
  const onScanDone = useCallback(async () => {
    if (!scanId) return;
    try {
      const res = await api.scanResult(scanId);
      setResult(res);
      setRowSelection({});
      toast.success(
        res.count === 0
          ? "Scan complete — nothing to clean."
          : `Found ${res.count} candidate${res.count === 1 ? "" : "s"}.`,
      );
    } catch (e) {
      toast.error(explain(e));
    } finally {
      setScanning(false);
    }
  }, [scanId]);

  const onScanError = useCallback((d: ErrorEvent) => {
    toast.error(`Scan failed (${d.error}).`);
    setScanning(false);
  }, []);

  const scanStream = useJobStream(
    "scan",
    scanning ? scanId : null,
    onScanDone,
    onScanError,
  );

  // --- Apply stream ---
  const onApplyDone = useCallback((data: unknown) => {
    const summary = data as ApplyDoneEvent;
    const removed = new Set(pendingApplyIds.current);
    setResult((prev) =>
      prev
        ? {
            ...prev,
            rows: prev.rows.filter((r) => !removed.has(r.track_id)),
            count: prev.rows.filter((r) => !removed.has(r.track_id)).length,
          }
        : prev,
    );
    setRowSelection({});
    setApplying(false);
    toast.success(
      `Removed — ${summary.unliked} unliked, ${summary.removed_from_playlists} playlist entr${
        summary.removed_from_playlists === 1 ? "y" : "ies"
      } across ${summary.playlists_touched} playlist${
        summary.playlists_touched === 1 ? "" : "s"
      }.`,
    );
    // The removal succeeded but its safety net didn't: say so plainly, because
    // Spotify offers no undo and there's now no restore manifest to fall back on.
    if (summary.backup_written === false) {
      toast.warning(
        "No restore manifest could be written, so this removal can't be undone from a backup.",
      );
    }
  }, []);

  const onApplyError = useCallback((d: ErrorEvent) => {
    toast.error(`Removal failed (${d.error}).`);
    setApplying(false);
  }, []);

  const applyStream = useJobStream(
    "apply",
    applying ? applyId : null,
    onApplyDone,
    onApplyError,
  );

  // --- Derived selection ---
  const selectedRows = useMemo(
    () => (result ? result.rows.filter((r) => rowSelection[r.track_id]) : []),
    [result, rowSelection],
  );
  const selectedIds = useMemo(
    () => selectedRows.map((r) => r.track_id),
    [selectedRows],
  );
  const hasLiked = selectedRows.some((r) => r.is_liked);
  const hasPlaylist = selectedRows.some((r) => r.playlist_count > 0);
  // Distinct playlists the removal would touch, so the dialog can say exactly
  // how wide the blast radius is before you type DELETE.
  const affectedPlaylists = useMemo(() => {
    const ids = new Set<string>();
    for (const r of selectedRows) for (const pid of r.playlist_ids) ids.add(pid);
    return ids.size;
  }, [selectedRows]);

  // --- Handlers ---
  const handleConnect = () => {
    if (!configured) {
      toast.error("Configure your Spotify app first.");
      return;
    }
    window.location.href = api.loginUrl(profile);
  };

  const handleDisconnect = async () => {
    try {
      await api.logout(profile);
      setAuth({ profile, connected: false });
      setResult(null);
      setRowSelection({});
      toast.success("Disconnected.");
      refreshProfiles();
    } catch (e) {
      toast.error(explain(e));
    }
  };

  const handleScan = async (values: ScanFormValues) => {
    if (!auth?.connected) {
      toast.error("Connect Spotify first.");
      return;
    }
    setResult(null);
    setRowSelection({});
    try {
      const { job_id } = await api.startScan({ ...values, profile });
      setScanId(job_id);
      setScanning(true);
    } catch (e) {
      toast.error(explain(e));
    }
  };

  const handleConfirmApply = async (opts: {
    unlike: boolean;
    removeFromPlaylists: boolean;
  }) => {
    if (!scanId || selectedIds.length === 0) return;
    pendingApplyIds.current = selectedIds;
    setApplyOpen(false);
    try {
      const { job_id } = await api.startApply({
        scan_job_id: scanId,
        profile,
        track_ids: selectedIds,
        unlike: opts.unlike,
        remove_from_playlists: opts.removeFromPlaylists,
        confirm: "DELETE",
      });
      setApplyId(job_id);
      setApplying(true);
    } catch (e) {
      toast.error(explain(e));
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6">
      <ProfileBar
        profiles={profiles}
        profile={profile}
        auth={auth}
        loading={authLoading}
        onProfileChange={setProfile}
        onConnect={handleConnect}
        onDisconnect={handleDisconnect}
      />

      {config && !configured ? (
        <SetupBanner redirectUri={config.redirect_uri} />
      ) : (
        <>
          <ScanForm
            disabled={!auth?.connected || scanning}
            scanning={scanning}
            onScan={handleScan}
          />

          {scanning && (
            <ProgressPanel
              title="Scanning your library"
              phase={scanStream.phase}
              progress={scanStream.progress}
              log={scanStream.log}
            />
          )}

          {applying && (
            <ProgressPanel
              title="Removing tracks"
              phase={applyStream.phase}
              progress={applyStream.progress}
              log={applyStream.log}
            />
          )}

          {result && !scanning && (
            <CandidateTable
              result={result}
              scanId={scanId ?? ""}
              rowSelection={rowSelection}
              onRowSelectionChange={setRowSelection}
              onApplyClick={() => setApplyOpen(true)}
              applying={applying}
            />
          )}
        </>
      )}

      <ConfirmApplyDialog
        open={applyOpen}
        onOpenChange={setApplyOpen}
        selectedCount={selectedIds.length}
        hasLiked={hasLiked}
        hasPlaylist={hasPlaylist}
        playlistCount={affectedPlaylists}
        applying={applying}
        onConfirm={handleConfirmApply}
      />

      <footer className="pt-2 text-center text-xs text-muted-foreground">
        Runs entirely on your machine. Your Spotify token never leaves this
        server.
      </footer>
    </div>
  );
}
