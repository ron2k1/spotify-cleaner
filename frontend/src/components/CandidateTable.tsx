import {
  type CSSProperties,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  type ColumnDef,
  type OnChangeFn,
  type RowSelectionState,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  ArrowDown,
  ArrowUp,
  ChevronsUpDown,
  Download,
  Heart,
  Music2,
  Search,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { ScanResult, TrackRow } from "@/lib/types";
import { cn, formatCount, formatDate } from "@/lib/utils";

const ROW_HEIGHT = 56;

// Confidence is text + colour, never colour alone, so it survives both
// colour-blindness and a screen reader. Rank drives the sort (high first).
const CONF: Record<string, { label: string; rank: number; className: string }> =
  {
    high: { label: "High", rank: 2, className: "bg-primary/15 text-primary" },
    medium: {
      label: "Medium",
      rank: 1,
      className: "bg-amber-500/15 text-amber-500",
    },
    low: {
      label: "Low",
      rank: 0,
      className: "bg-muted text-muted-foreground",
    },
  };

const CONF_TITLE: Record<string, string> = {
  high: "High — an exact, unambiguous match (e.g. a Spotify-id play event).",
  medium: "Medium — a fuzzier match or an indirect signal; sanity-check it.",
  low: "Low — a coarse 'top vs not' signal that can't tell rare from never-played.",
};

interface CandidateTableProps {
  result: ScanResult;
  scanId: string;
  rowSelection: RowSelectionState;
  onRowSelectionChange: OnChangeFn<RowSelectionState>;
  onApplyClick: () => void;
  applying: boolean;
}

function TrackCell({ row }: { row: TrackRow }) {
  // album_art_url always points at the lazy /api/art proxy, which 404s for any
  // track Spotify has no oEmbed thumbnail for. Swap to the placeholder on that
  // error rather than show a broken-image icon.
  const [artFailed, setArtFailed] = useState(false);
  return (
    <div className="flex min-w-0 items-center gap-3">
      {row.album_art_url && !artFailed ? (
        <img
          src={row.album_art_url}
          alt=""
          loading="lazy"
          onError={() => setArtFailed(true)}
          className="size-10 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="grid size-10 shrink-0 place-items-center rounded bg-muted text-muted-foreground">
          <Music2 className="size-4" />
        </div>
      )}
      <div className="min-w-0">
        <div className="truncate font-medium">{row.name}</div>
        <div className="truncate text-xs text-muted-foreground">
          {row.artist_label}
        </div>
      </div>
    </div>
  );
}

/** Track column flexes to fill; the rest are fixed-width so the flex rows line
 *  up with the (also flex) header row. */
function colStyle(id: string, size: number): CSSProperties {
  return id === "track"
    ? { flex: 1, minWidth: 200 }
    : { width: size, flexShrink: 0 };
}

export function CandidateTable({
  result,
  scanId,
  rowSelection,
  onRowSelectionChange,
  onApplyClick,
  applying,
}: CandidateTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  // Filter client-side: the whole result set is already in memory, and keying
  // rows by track_id (getRowId below) means a selection made before filtering
  // survives it -- rows filtered out of view stay selected, so "search, select
  // the matches, clear search, search again" accumulates rather than resets.
  const data = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return result.rows;
    return result.rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.artist_label.toLowerCase().includes(q) ||
        r.reason.toLowerCase().includes(q),
    );
  }, [result.rows, query]);

  // "/" focuses search from anywhere (unless you're already typing); Escape
  // clears the box. Kept tiny on purpose -- power-user speed without stealing
  // keys a screen-reader or form needs.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = document.activeElement;
      const typing =
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        (el instanceof HTMLElement && el.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "Escape" && el === searchRef.current) {
        setQuery("");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const columns = useMemo<ColumnDef<TrackRow>[]>(
    () => [
      {
        id: "select",
        size: 44,
        enableSorting: false,
        header: ({ table }) => (
          <Checkbox
            checked={table.getIsAllRowsSelected()}
            indeterminate={
              !table.getIsAllRowsSelected() && table.getIsSomeRowsSelected()
            }
            onChange={table.getToggleAllRowsSelectedHandler()}
            aria-label="Select all shown"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            aria-label={`Select ${row.original.name}`}
          />
        ),
      },
      {
        id: "track",
        header: "Track",
        enableSorting: false,
        cell: ({ row }) => <TrackCell row={row.original} />,
      },
      {
        id: "reason",
        header: "Why flagged",
        size: 220,
        enableSorting: false,
        cell: ({ row }) => (
          <span
            className="truncate text-muted-foreground"
            title={row.original.reason}
          >
            {row.original.reason}
          </span>
        ),
      },
      {
        id: "confidence",
        header: "Confidence",
        size: 116,
        // Sort by trust, not alphabetically: high > medium > low.
        accessorFn: (r) => CONF[r.confidence]?.rank ?? -1,
        cell: ({ row }) => {
          const c = CONF[row.original.confidence];
          if (!c) return <span className="text-muted-foreground">—</span>;
          return (
            <span
              className={cn(
                "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                c.className,
              )}
              title={CONF_TITLE[row.original.confidence]}
            >
              {c.label}
            </span>
          );
        },
      },
      {
        id: "plays",
        header: "Plays",
        size: 80,
        accessorFn: (r) => r.play_count ?? Number.POSITIVE_INFINITY,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {formatCount(row.original.play_count)}
          </span>
        ),
      },
      {
        id: "last",
        header: "Last played",
        size: 120,
        accessorFn: (r) => (r.last_played ? Date.parse(r.last_played) : 0),
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatDate(row.original.last_played)}
          </span>
        ),
      },
      {
        id: "added",
        header: "Added",
        size: 112,
        // Missing dates sort last (+Inf) so the default ascending order shows
        // the songs you've kept longest first — matching the planner's order.
        accessorFn: (r) =>
          r.added_at ? Date.parse(r.added_at) : Number.POSITIVE_INFINITY,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatDate(row.original.added_at)}
          </span>
        ),
      },
      {
        id: "playlists",
        header: "Playlists",
        size: 88,
        accessorFn: (r) => r.playlist_count,
        cell: ({ row }) => (
          <span className="tabular-nums">
            {formatCount(row.original.playlist_count)}
          </span>
        ),
      },
      {
        id: "liked",
        header: "Liked",
        size: 60,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.is_liked ? (
            <Heart
              className="size-4 fill-primary text-primary"
              aria-label="Liked"
            />
          ) : (
            <span className="text-muted-foreground" aria-label="Not liked">
              —
            </span>
          ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data,
    columns,
    state: { rowSelection, sorting },
    enableRowSelection: true,
    onRowSelectionChange,
    onSortingChange: setSorting,
    getRowId: (r) => r.track_id,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const tableRows = table.getRowModel().rows;
  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  const selectedCount = Object.values(rowSelection).filter(Boolean).length;
  const filtering = query.trim().length > 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {filtering ? (
            <>
              <span className="font-medium text-foreground">
                {data.length}
              </span>{" "}
              of {result.count} shown
            </>
          ) : (
            <>
              <span className="font-medium text-foreground">
                {result.count}
              </span>{" "}
              candidate{result.count === 1 ? "" : "s"}
            </>
          )}{" "}
          via <Badge variant="muted">{result.source}</Badge>
          {selectedCount > 0 && (
            <>
              {" · "}
              <span className="font-medium text-foreground">
                {selectedCount}
              </span>{" "}
              selected
            </>
          )}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter  /"
              aria-label="Filter candidates by track, artist, or reason"
              spellCheck={false}
              autoComplete="off"
              className="h-9 w-44 pl-8 pr-8"
            />
            {filtering && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  searchRef.current?.focus();
                }}
                aria-label="Clear filter"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>

          <a
            href={api.exportCsvUrl(scanId)}
            download
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              result.count === 0 && "pointer-events-none opacity-50",
            )}
            aria-disabled={result.count === 0}
            // pointer-events-none only blocks the mouse; without this a keyboard
            // user could still Tab to and trigger the "disabled" link, so the
            // aria-disabled state would be a lie. -1 removes it from tab order.
            tabIndex={result.count === 0 ? -1 : undefined}
          >
            <Download />
            CSV
          </a>

          {selectedCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => table.resetRowSelection()}
            >
              Clear
            </Button>
          )}
          <Button
            variant="destructive"
            size="sm"
            disabled={selectedCount === 0 || applying}
            onClick={onApplyClick}
          >
            <Trash2 />
            Remove{selectedCount > 0 ? ` ${selectedCount}` : ""} selected
          </Button>
        </div>
      </div>

      {result.count === 0 ? (
        <div className="rounded-lg border border-border bg-card p-10 text-center text-sm text-muted-foreground">
          Nothing flagged — by this measure, you listen to everything you saved.
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-10 text-center text-sm text-muted-foreground">
          No candidates match “{query.trim()}”.
        </div>
      ) : (
        <div
          ref={parentRef}
          role="region"
          aria-label="Cleanup candidates"
          className="max-h-[60vh] overflow-auto rounded-lg border border-border"
        >
          <table className="w-full text-sm" style={{ display: "grid" }}>
            <thead className="sticky top-0 z-10 grid bg-card/95 backdrop-blur">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="flex w-full border-b border-border">
                  {hg.headers.map((header) => {
                    const sorted = header.column.getIsSorted();
                    return (
                      <th
                        key={header.id}
                        style={colStyle(header.column.id, header.getSize())}
                        aria-sort={
                          sorted === "asc"
                            ? "ascending"
                            : sorted === "desc"
                              ? "descending"
                              : header.column.getCanSort()
                                ? "none"
                                : undefined
                        }
                        className="flex items-center px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground"
                      >
                        {header.isPlaceholder ? null : header.column.getCanSort() ? (
                          <button
                            type="button"
                            className="flex items-center gap-1 rounded-sm transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext(),
                            )}
                            {sorted === "asc" ? (
                              <ArrowUp className="size-3" />
                            ) : sorted === "desc" ? (
                              <ArrowDown className="size-3" />
                            ) : (
                              <ChevronsUpDown className="size-3 opacity-40" />
                            )}
                          </button>
                        ) : (
                          flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )
                        )}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody
              className="relative grid"
              style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
            >
              {rowVirtualizer.getVirtualItems().map((vr) => {
                const row = tableRows[vr.index];
                return (
                  <tr
                    key={row.id}
                    data-selected={row.getIsSelected()}
                    className="absolute flex w-full items-center border-b border-border/60 transition-colors hover:bg-accent/40 data-[selected=true]:bg-primary/10"
                    style={{
                      height: ROW_HEIGHT,
                      transform: `translateY(${vr.start}px)`,
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td
                        key={cell.id}
                        style={colStyle(cell.column.id, cell.column.getSize())}
                        className="flex items-center overflow-hidden px-3"
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
