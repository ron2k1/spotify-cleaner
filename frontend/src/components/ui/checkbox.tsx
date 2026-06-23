import * as React from "react";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface CheckboxProps extends Omit<React.ComponentProps<"input">, "type"> {
  /** Tri-state: a header checkbox is "indeterminate" when only some rows are
   *  selected. Native inputs only expose this via the DOM property, not an
   *  attribute, so we set it through a ref. */
  indeterminate?: boolean;
}

export function Checkbox({ className, indeterminate, ...props }: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = Boolean(indeterminate);
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      type="checkbox"
      className={cn(
        "size-4 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
