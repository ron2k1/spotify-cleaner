import { LogOut, Music, Plug, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AuthStatus, ProfileInfo } from "@/lib/types";

interface ProfileBarProps {
  profiles: ProfileInfo[];
  profile: string;
  auth: AuthStatus | null;
  loading: boolean;
  onProfileChange: (profile: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
}

/** Header: branding plus a profile picker. Each "profile" is a separate cached
 *  Spotify login, so a friend can connect under their own name and you switch
 *  between them with the datalist-backed input. */
export function ProfileBar({
  profiles,
  profile,
  auth,
  loading,
  onProfileChange,
  onConnect,
  onDisconnect,
}: ProfileBarProps) {
  const connected = Boolean(auth?.connected);

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-full bg-primary text-primary-foreground">
          <Music className="size-5" />
        </span>
        <div>
          <div className="font-semibold leading-tight">spotify-cleaner</div>
          <div className="text-xs text-muted-foreground">
            Find and remove the songs you never play.
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-muted-foreground" htmlFor="profile">
          Profile
        </label>
        <Input
          id="profile"
          list="profile-list"
          value={profile}
          onChange={(e) => onProfileChange(e.target.value)}
          className="h-8 w-36"
          placeholder="default"
          spellCheck={false}
          autoComplete="off"
        />
        <datalist id="profile-list">
          {profiles.map((p) => (
            <option key={p.id} value={p.id} />
          ))}
        </datalist>

        {connected ? (
          <>
            <Badge variant="default" className="gap-1.5">
              <span className="size-2 rounded-full bg-primary" />
              {auth?.display_name || profile}
            </Badge>
            <Button variant="outline" size="sm" onClick={onDisconnect}>
              <LogOut />
              Disconnect
            </Button>
          </>
        ) : (
          <Button size="sm" onClick={onConnect} disabled={loading}>
            {loading ? <RefreshCw className="animate-spin" /> : <Plug />}
            Connect Spotify
          </Button>
        )}
      </div>
    </header>
  );
}
