
import { Check, Circle, Lock } from "lucide-react";
import { cn } from "../../../Lib/utils.ts";

export type StepStatus = "completed" | "active" | "pending" | "locked";

interface Step {
  id: string;
  label: string;
  status: StepStatus;
}

interface StepProgressProps {
  steps: Step[];
}

export function StepProgress({ steps }: StepProgressProps) {
  return (
    <div className="flex items-center gap-2">
      {steps.map((step, index) => (
        <div key={step.id} className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full border text-xs font-bold transition-colors",
                step.status === "completed" && "border-primary bg-primary text-primary-foreground",
                step.status === "active" && "border-primary bg-primary/10 text-primary",
                step.status === "pending" && "border-border bg-secondary text-muted-foreground",
                step.status === "locked" && "border-border bg-secondary text-muted-foreground"
              )}
            >
              {step.status === "completed" ? (
                <Check className="h-4 w-4" />
              ) : step.status === "locked" ? (
                <Lock className="h-3 w-3" />
              ) : (
                <span>{index + 1}</span>
              )}
            </div>
            <span
              className={cn(
                "text-sm font-medium transition-colors",
                step.status === "completed" && "text-primary",
                step.status === "active" && "text-foreground",
                (step.status === "pending" || step.status === "locked") && "text-muted-foreground"
              )}
            >
              {step.label}
            </span>
          </div>
          {index < steps.length - 1 && (
            <div
              className={cn(
                "h-px w-8 transition-colors",
                step.status === "completed" ? "bg-primary" : "bg-border"
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}
