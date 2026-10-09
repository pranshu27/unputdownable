import { Button } from "../../CodeGen/CodeGenComponents/button.tsx";
import { StatusIndicator, ConnectionStatus } from "../CodeGenComponents/StatusIndicator.tsx";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../CodeGenComponents/select.tsx";
import { Check, LogIn, Settings, Ticket } from "lucide-react";
import type { JiraBoard, TargetPlatform } from "../../../types/api.ts";
import { PLATFORM_OPTIONS } from "../../../types/api.ts";

interface ContextPanelProps {
  isAuthenticated: boolean;
  connectionStatus: ConnectionStatus;
  boards: JiraBoard[];
  selectedBoard: JiraBoard | null;
  ticketKey: string | null;
  selectedPlatform: TargetPlatform | null;
  generatedCode: string | null;
  isCommitted: boolean;
  isCreatingTicket: boolean;
  onBoardChange: (board: JiraBoard) => void;
  onAuthClick: () => void;
  onCreateTicket: () => void;
}

export function ContextPanel({
  isAuthenticated,
  connectionStatus,
  boards,
  selectedBoard,
  ticketKey,
  selectedPlatform,
  generatedCode,
  isCommitted,
  isCreatingTicket,
  onBoardChange,
  onAuthClick,
  onCreateTicket,
}: ContextPanelProps) {
  const handleBoardChange = (boardId: string) => {
    const board = boards.find((b) => b.id === boardId);
    if (board) onBoardChange(board);
  };

  const completionRows = [
    ["Authenticated", isAuthenticated],
    ["Ticket Ready", Boolean(ticketKey)],
    ["Platform Selected", Boolean(selectedPlatform)],
    ["Code Generated", Boolean(generatedCode)],
    ["Committed", isCommitted],
  ];

  return (
    <aside className="enterprise-card p-5 flex flex-col w-full">
      <div>
        <div className="mb-4 flex items-center gap-2">
          <Settings className="h-4 w-4 text-primary" />
          <h2 className="font-bold text-foreground">Configuration</h2>
        </div>

        <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">JIRA Connection</label>
          <div className="flex items-center justify-between rounded-lg border border-border bg-secondary px-3 py-2.5">
            <StatusIndicator
              status={connectionStatus}
              label={
                connectionStatus === "connected"
                  ? "Connected"
                  : connectionStatus === "pending"
                    ? "Connecting"
                    : "Not connected"
              }
            />
            {!isAuthenticated && (
              <Button variant="outline" size="sm" onClick={onAuthClick}>
                <LogIn className="h-3 w-3" />
                Connect
              </Button>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">JIRA Board</label>
          <Select value={selectedBoard?.id || ""} onValueChange={handleBoardChange} disabled={!isAuthenticated}>
            <SelectTrigger className="h-9">
              <SelectValue placeholder={isAuthenticated ? "Select a board" : "Connect JIRA first"} />
            </SelectTrigger>
            <SelectContent>
              {boards.map((board) => (
                <SelectItem key={board.id} value={board.id}>
                  {board.name} ({board.key})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {ticketKey && (
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Current Ticket</label>
            <div className="rounded-lg border border-border bg-secondary px-3 py-2.5">
              <div className="flex items-center gap-2">
                <Check className="h-4 w-4 text-primary" />
                <span className="font-mono text-sm font-bold text-foreground">{ticketKey}</span>
              </div>
            </div>
          </div>
        )}

        {selectedPlatform && (
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Target Platform</label>
            <div className="rounded-lg border border-primary/25 bg-primary/10 px-3 py-2.5">
              <span className="text-sm font-bold text-primary">
                {PLATFORM_OPTIONS.find((p) => p.code === selectedPlatform)?.name}
              </span>
            </div>
          </div>
        )}

        </div>
      </div>

      <Button
        variant="outline"
        className="w-full mt-6"
        onClick={onCreateTicket}
        disabled={!isAuthenticated || !selectedBoard || isCreatingTicket}
      >
        {isCreatingTicket ? (
          <>
            <span className="enterprise-loader" />
            Creating Ticket
          </>
        ) : (
          <>
            <Ticket className="h-4 w-4" />
            Create Ticket
          </>
        )}
      </Button>
    </aside>
  );
}
