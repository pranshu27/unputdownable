import { cn } from "../../../Lib/utils.ts";

export type ConnectionStatus = "connected" | "disconnected" | "pending";

interface StatusIndicatorProps {
  status: ConnectionStatus;
  label: string;
}

export function StatusIndicator({ status, label }: StatusIndicatorProps) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={cn(
          "status-dot",
          status === "connected" && "connected",
          status === "disconnected" && "disconnected",
          status === "pending" && "pending"
        )}
      />
      <span
        className={cn(
          "text-sm",
          status === "connected" && "text-success",
          status === "disconnected" && "text-muted-foreground",
          status === "pending" && "text-warning"
        )}
      >
        {label}
      </span>
    </div>
  );
}
