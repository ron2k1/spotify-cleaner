import { AlertTriangle } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/** Shown when the server reports no Client ID/Secret. Walks the user through
 *  registering their own Spotify app and echoes the exact redirect URI to add. */
export function SetupBanner({ redirectUri }: { redirectUri: string }) {
  return (
    <Card className="border-amber-500/40 bg-amber-500/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-amber-400">
          <AlertTriangle className="size-5" />
          Spotify app not configured
        </CardTitle>
        <CardDescription>
          This tool talks to <em>your own</em> Spotify developer app, so your
          listening data never passes through anyone else&apos;s server.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm">
        <ol className="list-decimal space-y-3 pl-5 text-muted-foreground">
          <li>
            Open the{" "}
            <a
              className="text-primary underline"
              href="https://developer.spotify.com/dashboard"
              target="_blank"
              rel="noreferrer"
            >
              Spotify Developer Dashboard
            </a>{" "}
            and create an app.
          </li>
          <li>
            Add this exact Redirect URI:
            <div className="mt-1">
              <code className="rounded bg-muted px-2 py-1 text-foreground">
                {redirectUri}
              </code>
            </div>
          </li>
          <li>
            Put the Client ID and Secret in a{" "}
            <code className="rounded bg-muted px-1">.env</code> next to the
            project:
            <pre className="mt-1 overflow-x-auto rounded bg-muted p-3 text-xs text-foreground">
              {`SPOTIFY_CLIENT_ID=your_id\nSPOTIFY_CLIENT_SECRET=your_secret`}
            </pre>
          </li>
          <li>Restart the server — this banner clears once the keys load.</li>
        </ol>
      </CardContent>
    </Card>
  );
}
