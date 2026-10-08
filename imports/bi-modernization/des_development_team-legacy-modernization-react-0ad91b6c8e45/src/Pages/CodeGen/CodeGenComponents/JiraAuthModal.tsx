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
import { Lock, Loader2, CheckCircle } from "lucide-react";

interface JiraAuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAuthenticate: (email: string, apiToken: string, domain: string) => Promise<void>;
}

export function JiraAuthModal({ isOpen, onClose, onAuthenticate }: JiraAuthModalProps) {
  const [email, setEmail] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [domain, setDomain] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await onAuthenticate(email, apiToken, domain);
      setIsSuccess(true);
      setTimeout(() => {
        onClose();
        setIsSuccess(false);
        setEmail("");
        setApiToken("");
        setDomain("");
      }, 1500);
    } catch (error) {
      console.error("Authentication failed:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Lock className="h-5 w-5 text-primary" />
            JIRA Authentication
          </DialogTitle>
          <DialogDescription>
            Connect your JIRA account to create tickets and generate code.
          </DialogDescription>
        </DialogHeader>
        
        <AnimatePresence mode="wait">
          {isSuccess ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex flex-col items-center justify-center py-8"
            >
              <CheckCircle className="h-16 w-16 text-success mb-4" />
              <p className="text-lg font-medium text-success">Successfully Connected!</p>
            </motion.div>
          ) : (
            <motion.form
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onSubmit={handleSubmit}
              className="space-y-4 py-4"
            >
              <div className="space-y-2">
                <Label htmlFor="domain">JIRA Domain</Label>
                <Input
                  id="domain"
                  placeholder="your-company.atlassian.net"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="email">Email Address</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="token">API Token</Label>
                <Input
                  id="token"
                  type="password"
                  placeholder="Your JIRA API token"
                  value={apiToken}
                  onChange={(e) => setApiToken(e.target.value)}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Generate an API token from your{" "}
                  <a
                    href="https://id.atlassian.com/manage-profile/security/api-tokens"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    Atlassian account settings
                  </a>
                </p>
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
                  disabled={isLoading}
                  className="flex-1"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Connecting...
                    </>
                  ) : (
                    "Connect JIRA"
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
