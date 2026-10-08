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
import { BarChart2, Loader2, Download, Table, Database, FileSpreadsheet } from "lucide-react";

interface PowerBIModalProps {
  isOpen: boolean;
  onClose: () => void;
  ticketKey: string;
  onGenerate: (details: PowerBIDetails) => Promise<void>;
}

export interface PowerBIDetails {
  dataSource: string;
  connectionString: string;
  tables: string[];
  measures: string;
  outputFormat: "pbix" | "pbit" | "dax";
}

export function PowerBIModal({
  isOpen,
  onClose,
  ticketKey,
  onGenerate,
}: PowerBIModalProps) {
  const [dataSource, setDataSource] = useState("sql-server");
  const [connectionString, setConnectionString] = useState("");
  const [tables, setTables] = useState("");
  const [measures, setMeasures] = useState("");
  const [outputFormat, setOutputFormat] = useState<"pbix" | "pbit" | "dax">("dax");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await onGenerate({
        dataSource,
        connectionString,
        tables: tables.split(",").map((t) => t.trim()).filter(Boolean),
        measures,
        outputFormat,
      });
      onClose();
    } catch (error) {
      console.error("PowerBI generation failed:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <BarChart2 className="h-5 w-5 text-primary" />
            PowerBI Configuration
          </DialogTitle>
          <DialogDescription>
            Configure your PowerBI report settings for ticket {ticketKey}
          </DialogDescription>
        </DialogHeader>

        <motion.form
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          onSubmit={handleSubmit}
          className="space-y-4 py-4"
        >
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="dataSource">Data Source</Label>
              <Select value={dataSource} onValueChange={setDataSource}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="sql-server">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4" />
                      SQL Server
                    </div>
                  </SelectItem>
                  <SelectItem value="azure-synapse">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4" />
                      Azure Synapse
                    </div>
                  </SelectItem>
                  <SelectItem value="bigquery">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4" />
                      BigQuery
                    </div>
                  </SelectItem>
                  <SelectItem value="excel">
                    <div className="flex items-center gap-2">
                      <FileSpreadsheet className="h-4 w-4" />
                      Excel
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="outputFormat">Output Format</Label>
              <Select value={outputFormat} onValueChange={(v) => setOutputFormat(v as typeof outputFormat)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="dax">DAX Measures</SelectItem>
                  <SelectItem value="pbit">PBIT Template</SelectItem>
                  <SelectItem value="pbix">PBIX File</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="connectionString">Connection String</Label>
            <Input
              id="connectionString"
              placeholder="Server=myserver;Database=mydb;..."
              value={connectionString}
              onChange={(e) => setConnectionString(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="tables">
              <div className="flex items-center gap-2">
                <Table className="h-4 w-4" />
                Tables (comma-separated)
              </div>
            </Label>
            <Input
              id="tables"
              placeholder="Sales, Products, Customers"
              value={tables}
              onChange={(e) => setTables(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="measures">Custom DAX Measures (optional)</Label>
            <Textarea
              id="measures"
              placeholder="Total Sales = SUM(Sales[Amount])&#10;YTD Sales = TOTALYTD([Total Sales], 'Date'[Date])"
              value={measures}
              onChange={(e) => setMeasures(e.target.value)}
              rows={4}
              className="resize-none font-mono text-sm"
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
              disabled={isLoading}
              className="flex-1"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" />
                  Generate {outputFormat.toUpperCase()}
                </>
              )}
            </Button>
          </div>
        </motion.form>
      </DialogContent>
    </Dialog>
  );
}
