import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../CodeGenComponents/dialog.tsx";
import { Button } from "../CodeGenComponents/button.tsx";
import { Check, Database, Layers, BarChart2, Zap, Cpu, Loader2 } from "lucide-react";
import { cn } from "../../../Lib/utils.ts";
import type { TargetPlatform, PlatformOption } from "../../../types/api.ts";
import { PLATFORM_OPTIONS } from "../../../types/api.ts";

interface PlatformSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (platform: TargetPlatform) => void;
  isGenerating?: boolean;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  database: Database,
  layers: Layers,
  "bar-chart-2": BarChart2,
  zap: Zap,
  cpu: Cpu,
};

export function PlatformSelectionModal({
  isOpen,
  onClose,
  onSelect,
  isGenerating,
}: PlatformSelectionModalProps) {
  const [selectedPlatform, setSelectedPlatform] = useState<TargetPlatform | null>(null);

  const handleConfirm = () => {
    if (selectedPlatform) {
      onSelect(selectedPlatform);
      setSelectedPlatform(null); // Reset for next time
    }
  };

  const handleClose = () => {
    setSelectedPlatform(null);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Zap className="h-5 w-5 text-primary" />
            Select Target Platform
          </DialogTitle>
          <DialogDescription>
            Choose the technology for code generation. This selection is required before generating code.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {PLATFORM_OPTIONS.map((platform) => {
              const Icon = iconMap[platform.icon] || Database;
              const isSelected = selectedPlatform === platform.code;

              return (
                <button
                  key={platform.code}
                  onClick={() => setSelectedPlatform(platform.code)}
                  className={cn(
                    "relative p-4 rounded-xl border transition-all duration-200 text-left",
                    isSelected
                      ? "border-primary bg-primary/10"
                      : "border-border/50 bg-secondary/30 hover:border-primary/50 hover:bg-secondary/50"
                  )}
                >
                  {isSelected && (
                    <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                      <Check className="h-3 w-3 text-primary-foreground" />
                    </div>
                  )}
                  
                  <div
                    className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center mb-3 transition-colors",
                      isSelected
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary text-muted-foreground"
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </div>
                  
                  <h4 className={cn(
                    "font-medium text-sm mb-0.5 transition-colors",
                    isSelected ? "text-primary" : "text-foreground"
                  )}>
                    {platform.name}
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    {platform.description}
                  </p>
                </button>
              );
            })}
          </div>

          {selectedPlatform && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              className="mt-4 flex items-center gap-2"
            >
              <div className="px-3 py-1.5 rounded-full bg-primary/10 border border-primary/30 text-primary text-xs font-medium flex items-center gap-2">
                <Check className="h-3 w-3" />
                {PLATFORM_OPTIONS.find((p) => p.code === selectedPlatform)?.name} Selected
              </div>
            </motion.div>
          )}
        </div>

        <div className="flex gap-3 pt-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleClose}
            className="flex-1"
            disabled={isGenerating}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="glow"
            onClick={handleConfirm}
            disabled={!selectedPlatform || isGenerating}
            className="flex-1"
          >
            {isGenerating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Zap className="h-4 w-4" />
                Generate Code
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
