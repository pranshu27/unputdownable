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
import { Input } from "../CodeGenComponents/input.tsx";
import { Label } from "../CodeGenComponents/label.tsx";
import { Textarea } from "../CodeGenComponents/textarea.tsx";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../CodeGenComponents/select.tsx";
import { Ticket, Loader2, CheckCircle } from "lucide-react";

interface Board {
  id: string;
  name: string;
}

interface CreateTicketModalProps {
  isOpen: boolean;
  onClose: () => void;
  boards: Board[];
  onCreateTicket: (data: {
    board: string;
    summary: string;
    description: string;
    issueType: string;
  }) => Promise<string>;
}

export function CreateTicketModal({
  isOpen,
  onClose,
  boards,
  onCreateTicket,
}: CreateTicketModalProps) {
  const [selectedBoard, setSelectedBoard] = useState("");
  const [summary, setSummary] = useState("");
  const [description, setDescription] = useState("");
  const [issueType, setIssueType] = useState("Story");
  const [isLoading, setIsLoading] = useState(false);
  const [createdTicket, setCreatedTicket] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const ticketKey = await onCreateTicket({
        board: selectedBoard,
        summary,
        description,
        issueType,
      });
      setCreatedTicket(ticketKey);
      setTimeout(() => {
        onClose();
        setCreatedTicket(null);
        setSummary("");
        setDescription("");
        setSelectedBoard("");
      }, 1500);
    } catch (error) {
      console.error("Failed to create ticket:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Ticket className="h-5 w-5 text-primary" />
            Create JIRA Ticket
          </DialogTitle>
          <DialogDescription>
            Create a new ticket to track your code generation task.
          </DialogDescription>
        </DialogHeader>

        <AnimatePresence mode="wait">
          {createdTicket ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex flex-col items-center justify-center py-8"
            >
              <CheckCircle className="h-16 w-16 text-success mb-4" />
              <p className="text-lg font-medium text-success">Ticket Created!</p>
              <p className="text-sm text-muted-foreground mt-1">
                Issue Key: <span className="font-mono text-primary">{createdTicket}</span>
              </p>
            </motion.div>
          ) : (
            <motion.form
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onSubmit={handleSubmit}
              className="space-y-4 py-4"
            >
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="board">Board</Label>
                  <Select value={selectedBoard} onValueChange={setSelectedBoard}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select board" />
                    </SelectTrigger>
                    <SelectContent>
                      {boards.map((board) => (
                        <SelectItem key={board.id} value={board.id}>
                          {board.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="summary">Summary</Label>
                <Input
                  id="summary"
                  placeholder="Brief description of the task"
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  placeholder="Detailed description of what needs to be done..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  className="resize-none"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onClose}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="glow"
                  disabled={isLoading || !selectedBoard || !summary}
                  className="flex-1"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    "Create Ticket"
                  )}
                </Button>
              </div>
            </motion.form>
          )}
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  );
}
