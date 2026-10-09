import { BarChart2, Check, Cpu, Database, GitMerge, Layers, Zap } from "lucide-react";
import { cn } from "../../../Lib/utils.ts";
import type { TargetPlatform } from "../../../types/api.ts";
import { PLATFORM_OPTIONS } from "../../../types/api.ts";

interface PlatformSelectorProps {
  selectedPlatform: TargetPlatform | null;
  onSelect: (platform: TargetPlatform) => void;
  disabled?: boolean;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  database: Database,
  layers: Layers,
  "bar-chart-2": BarChart2,
  zap: Zap,
  cpu: Cpu,
  "git-merge": GitMerge,
};

export function PlatformSelector({ selectedPlatform, onSelect, disabled }: PlatformSelectorProps) {
  return (
    <section className="enterprise-card p-6">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-foreground">Target Platform</h3>
        <p className="mt-1 text-xs font-medium text-muted-foreground">
          Select the output technology for the generated implementation.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {PLATFORM_OPTIONS.map((platform) => {
          const Icon = iconMap[platform.icon] || Database;
          const isSelected = selectedPlatform === platform.code;

          return (
            <button
              key={platform.code}
              onClick={() => !disabled && onSelect(platform.code)}
              disabled={disabled}
              className={cn(
                "relative rounded-xl border p-4 text-left transition-colors",
                isSelected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-card hover:bg-secondary",
                disabled && "cursor-not-allowed opacity-50"
              )}
            >
              {isSelected && (
                <span className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Check className="h-3 w-3" />
                </span>
              )}

              <div className={cn(
                "mb-3 flex h-9 w-9 items-center justify-center rounded-lg border",
                isSelected ? "border-primary bg-primary text-primary-foreground" : "border-border bg-secondary text-muted-foreground"
              )}>
                <Icon className="h-4 w-4" />
              </div>

              <h4 className={cn("text-sm font-bold", isSelected ? "text-primary" : "text-foreground")}>
                {platform.name}
              </h4>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{platform.description}</p>
            </button>
          );
        })}
      </div>

      {selectedPlatform && (
        <div className="mt-4 inline-flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs font-bold text-primary">
          <Check className="h-3 w-3" />
          {PLATFORM_OPTIONS.find((p) => p.code === selectedPlatform)?.name} selected
        </div>
      )}
    </section>
  );
}
