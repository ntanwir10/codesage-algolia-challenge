import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon?: string;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick?: () => void;
    href?: string;
  };
  className?: string;
}

export function EmptyState({
  icon = "📁",
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={`text-center py-12 ${className || ""}`}>
      <div className="text-4xl mb-4">{icon}</div>
      <h2 className="text-xl font-semibold mb-2">{title}</h2>
      <p className="text-muted-foreground mb-4 max-w-md mx-auto">
        {description}
      </p>
      {action && (
        <Button onClick={action.onClick} asChild={!!action.href}>
          {action.href ? (
            <Link to={action.href}>{action.label}</Link>
          ) : (
            action.label
          )}
        </Button>
      )}
    </div>
  );
}
