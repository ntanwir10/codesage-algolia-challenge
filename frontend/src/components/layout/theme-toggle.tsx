import { useState } from "react";
import { Button } from "@/components/ui/button";

// index.html picks the starting theme before the first paint; this flips it and remembers the choice
export function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));

  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      // Storage blocked: the choice lasts until the page reloads
    }
    setDark(next);
  };

  const label = dark ? "Switch to light mode" : "Switch to dark mode";
  return (
    <Button variant="ghost" size="sm" onClick={toggle} aria-label={label} title={label}>
      <span aria-hidden="true">{dark ? "☀" : "☾"}</span>
    </Button>
  );
}
