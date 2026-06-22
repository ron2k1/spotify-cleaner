import { type CSSProperties, useMemo, useRef, useState } from "react";
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
  Heart,
  Music2,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { ScanResult, TrackRow } from "@/lib/types";
import { formatCount, formatDate } from "@/lib/utils";

const ROW_HEIGHT = 56;

interface CandidateTableProps {
  result: ScanResult;
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
  rowSelection,
  onRowSelectionChange,
  onApplyClick,
  applying,
}: CandidateTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);

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
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            aria-label="Select row"
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
        size: 240,
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
        id: "plays",
        header: "Plays",
        size: 88,
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
        size: 128,
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
        size: 116,
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
        size: 92,
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
        size: 64,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.is_liked ? (
            <Heart className="size-4 fill-primary text-primary" />
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: result.rows,
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

  const selectedCount = table.getSelectedRowModel().rows.length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{result.count}</span>{" "}
          candidate{result.count === 1 ? "" : "s"} via{" "}
          <Badge variant="muted">{result.source}</Badge>
          {selectedCount > 0 && (
            <>
              {" · "}
              <span className="font-medium text-foreground">
                {selectedCount}
              </span>{" "}
              selected
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
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
      ) : (
        <div
          ref={parentRef}
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
                        className="flex items-center px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground"
                      >
                        {header.isPlaceholder ? null : header.column.getCanSort() ? (
                          <button
                            type="button"
                            className="flex items-center gap-1 transition-colors hover:text-foreground"
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
