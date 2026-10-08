import { Code2, Moon, Sun } from "lucide-react";

interface HeaderProps {
  theme: "light" | "dark";
  onThemeToggle: () => void;
}

export function Header({ theme, onThemeToggle }: HeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Code2 className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-normal text-foreground">Code Generation</h1>
            <p className="text-xs font-medium text-muted-foreground">JNJ enterprise modernization workspace</p>
          </div>
        </div>

        <button type="button" className="codegen-theme-toggle" onClick={onThemeToggle}>
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </div>
    </header>
  );
}
