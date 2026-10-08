import { useState, useEffect } from "react";
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
import { GitBranch, Loader2, CheckCircle, ExternalLink, FolderGit2, FileCode } from "lucide-react";

interface GitHubCommitModalProps {
  isOpen: boolean;
  onClose: () => void;
  ticketKey: string;
  fileName: string;
  onCommit: (data: {
    repoUrl: string;
    token: string;
    branch: string;
    folder: string;
    fileName: string;
  }) => Promise<{ success: boolean; commitUrl?: string , branch?: string, jiraFolder?: string; message?: string }>;
}

export function GitHubCommitModal({
  isOpen,
  onClose,
  ticketKey,
  fileName,
  onCommit,
}: GitHubCommitModalProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [token, setToken] = useState("");
  const [branch, setBranch] = useState("ai-generated");
  const [folder, setFolder] = useState(ticketKey);
  const [customFileName, setCustomFileName] = useState(fileName);
  const [isLoading, setIsLoading] = useState(false);
  const [commitResult, setCommitResult] = useState<{
    success: boolean;
    commitUrl?: string;
    branch?: string;
    jiraFolder?: string;
  } | null>(null);

  // Auto-fill folder with ticket key
  useEffect(() => {
    setFolder(ticketKey);
  }, [ticketKey]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const result = await onCommit({
        repoUrl,
        token,
        branch,
        folder,
        fileName: customFileName,
      });
      console.log("Commit result:", result);
      setCommitResult(result);
      if (result.success) {
        setTimeout(() => {
          onClose();
          setCommitResult(null);
          setRepoUrl("");
          setToken("");
          setBranch("ai-generated");
        }, 10000);
      }
    } catch (error) {
      console.error("Commit failed:", error);
      setCommitResult({ success: false });
    } finally {
      setIsLoading(false);
    }
  };

  
  const handleOpenInGitHub = () => {
    console.log("Opening commit URL:", commitResult?.commitUrl);
    if (commitResult?.commitUrl) {
      window.open(`${commitResult.commitUrl}/tree/${commitResult.branch}/${commitResult.jiraFolder}`);
    }
  };

  const handleOpenInGitHub1s = () => {
    if (commitResult?.commitUrl) {
      const temp = commitResult.commitUrl.replace("github.com", "github1s.com");
      window.open(`${temp}/tree/${commitResult.branch}/${commitResult.jiraFolder}`);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <GitBranch className="h-5 w-5 text-primary" />
            Commit to GitHub
          </DialogTitle>
          <DialogDescription>
            Push the generated code to your GitHub repository.
          </DialogDescription>
        </DialogHeader>

        <AnimatePresence mode="wait">
          {commitResult?.success ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 1 }} 
              className="flex flex-col items-center justify-center py-8"
            >
              <CheckCircle className="h-16 w-16 text-success mb-4" />
              <p className="text-lg font-medium text-success mb-2">
                Successfully Committed!
              </p>
              <p className="text-sm text-muted-foreground mb-4">
                Your code has been pushed to GitHub
              </p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={handleOpenInGitHub}>
                  <ExternalLink className="h-4 w-4 mr-1.5" />
                  View on GitHub
                </Button>
                <Button variant="outline" size="sm" onClick={handleOpenInGitHub1s}>
                  <ExternalLink className="h-4 w-4 mr-1.5" />
                  Open in GitHub1s
                </Button>
              </div>
            </motion.div>
          ) : (
            <motion.form
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onSubmit={handleSubmit}
                transition={{ duration: 1 }} 
              className="space-y-4 py-4"
            >
              <div className="space-y-2">
                <Label htmlFor="repoUrl">Repository URL</Label>
                <Input
                  id="repoUrl"
                  placeholder="https://github.com/username/repo"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="token">Personal Access Token</Label>
                <Input
                  id="token"
                  type="password"
                  placeholder="ghp_xxxxxxxxxxxx"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Generate a token from{" "}
                  <a
                    href="https://github.com/settings/tokens"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    GitHub Settings
                  </a>
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="branch">Branch</Label>
                  <div className="relative">
                    <GitBranch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="branch"
                      className="pl-9"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="folder">Folder</Label>
                  <div className="relative">
                    <FolderGit2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="folder"
                      className="pl-9"
                      value={folder}
                      onChange={(e) => setFolder(e.target.value)}
                      required
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="fileName">File Name</Label>
                <div className="relative">
                  <FileCode className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="fileName"
                    className="pl-9"
                    value={customFileName}
                    onChange={(e) => setCustomFileName(e.target.value)}
                    required
                  />
                </div>
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
                  disabled={isLoading || !repoUrl || !token}
                  className="flex-1"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Committing...
                    </>
                  ) : (
                    <>
                      <GitBranch className="h-4 w-4" />
                      Commit Code
                    </>
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
