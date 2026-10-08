import { Check, Circle, Lock } from "lucide-react";
import { cn } from "../../../Lib/utils.ts";

interface WorkflowStep {
  id: string;
  label: string;
  status: "completed" | "active" | "pending" | "locked";
}

interface WorkflowStatusBarProps {
  isAuthenticated: boolean;
  hasTicket: boolean;
  hasPlatform: boolean;
  hasCode: boolean;
  isCommitted: boolean;
}

export function WorkflowStatusBar({
  isAuthenticated,
  hasTicket,
  hasPlatform,
  hasCode,
  isCommitted,
}: WorkflowStatusBarProps) {
  const steps: WorkflowStep[] = [
    { id: "auth", label: "Authenticated", status: isAuthenticated ? "completed" : "active" },
    { id: "ticket", label: "Ticket Ready", status: !isAuthenticated ? "locked" : hasTicket ? "completed" : "active" },
    { id: "platform", label: "Platform Selected", status: !hasTicket ? "locked" : hasPlatform ? "completed" : "active" },
    { id: "code", label: "Code Generated", status: !hasPlatform ? "locked" : hasCode ? "completed" : "active" },
    { id: "commit", label: "Committed", status: !hasCode ? "locked" : isCommitted ? "completed" : "pending" },
  ];

  const getStatusIcon = (status: WorkflowStep["status"]) => {
    if (status === "completed") return <Check className="h-3 w-3" />;
    if (status === "locked") return <Lock className="h-3 w-3" />;
    return <Circle className={cn("h-2 w-2", status === "active" && "fill-current")} />;
  };

  return (
    <div className="border-b border-border bg-card px-4 py-3">
      <div className="flex w-full items-center justify-center gap-2 overflow-x-auto">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-center shrink-0">
            <div
              className={cn(
                "flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-bold shrink-0",
                step.status === "completed" && "border-primary bg-primary text-primary-foreground",
                step.status === "active" && "border-primary bg-primary/10 text-primary",
                step.status === "pending" && "border-border bg-secondary text-muted-foreground",
                step.status === "locked" && "border-border bg-secondary text-muted-foreground"
              )}
            >
              {getStatusIcon(step.status)}
              <span className="hidden sm:inline">{step.label}</span>
            </div>
            {index < steps.length - 1 && (
              <div className={cn("mx-1 h-px w-6 shrink-0", step.status === "completed" ? "bg-primary" : "bg-border")} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
