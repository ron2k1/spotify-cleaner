import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";

interface ConfirmApplyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCount: number;
  hasLiked: boolean;
  hasPlaylist: boolean;
  /** Distinct playlists the removal would touch — the blast radius. */
  playlistCount: number;
  applying: boolean;
  onConfirm: (opts: { unlike: boolean; removeFromPlaylists: boolean }) => void;
}

/** The irreversible step. Two independent gates: at least one action chosen,
 *  and the literal word DELETE typed. Radix focuses Cancel on open, so the
 *  destructive default is the safe one. */
export function ConfirmApplyDialog({
  open,
  onOpenChange,
  selectedCount,
  hasLiked,
  hasPlaylist,
  playlistCount,
  applying,
  onConfirm,
}: ConfirmApplyDialogProps) {
  const [unlike, setUnlike] = useState(true);
  const [removeFromPlaylists, setRemoveFromPlaylists] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  // Reset to sensible defaults whenever the dialog reopens for a new selection.
  useEffect(() => {
    if (open) {
      setUnlike(hasLiked);
      setRemoveFromPlaylists(!hasLiked && hasPlaylist);
      setConfirmText("");
    }
  }, [open, hasLiked, hasPlaylist]);

  const actionChosen = unlike || removeFromPlaylists;
  const canApply = actionChosen && confirmText === "DELETE" && !applying;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <Trash2 className="size-5 text-destructive" />
            Remove {selectedCount} track{selectedCount === 1 ? "" : "s"}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            This cannot be undone from here. Choose what to remove, then type{" "}
            <code className="rounded bg-muted px-1 text-foreground">DELETE</code>{" "}
            to confirm.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3">
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              className="mt-0.5"
              checked={unlike}
              disabled={!hasLiked}
              onChange={(e) => setUnlike(e.target.checked)}
            />
            <span>
              Unlike from <strong>Liked Songs</strong>
              {!hasLiked && (
                <span className="text-muted-foreground">
                  {" "}
                  — none of the selected are liked
                </span>
              )}
            </span>
          </label>

          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              className="mt-0.5"
              checked={removeFromPlaylists}
              disabled={!hasPlaylist}
              onChange={(e) => setRemoveFromPlaylists(e.target.checked)}
            />
            <span>
              Remove from <strong>your playlists</strong>
              {hasPlaylist ? (
                <span className="text-muted-foreground">
                  {" "}
                  — affects {playlistCount} playlist
                  {playlistCount === 1 ? "" : "s"}
                </span>
              ) : (
                <span className="text-muted-foreground">
                  {" "}
                  — none of the selected are in your playlists
                </span>
              )}
            </span>
          </label>

          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="Type DELETE"
            autoComplete="off"
            spellCheck={false}
            aria-label="Type DELETE to confirm"
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={buttonVariants({ variant: "destructive" })}
            disabled={!canApply}
            onClick={() => onConfirm({ unlike, removeFromPlaylists })}
          >
            Remove {selectedCount} track{selectedCount === 1 ? "" : "s"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
