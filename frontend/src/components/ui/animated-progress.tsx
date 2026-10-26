import { useEffect, useRef, useState } from "react";

interface AnimatedProgressProps {
  value: number; // 0-100
  max?: number;
  className?: string;
  showLabel?: boolean;
  animated?: boolean;
  color?: "blue" | "green" | "yellow" | "red";
  size?: "sm" | "md" | "lg";
  indeterminate?: boolean;
}

export function AnimatedProgress({
  value,
  max = 100,
  className = "",
  showLabel = true,
  animated = true,
  color = "blue",
  size = "md",
  indeterminate = false,
}: AnimatedProgressProps) {
  const [displayValue, setDisplayValue] = useState(0);
  const displayRef = useRef(0);

  // Animate from the previous displayed value to the target value
  useEffect(() => {
    const endValue = Math.min(value, max);

    if (!animated) {
      displayRef.current = endValue;
      setDisplayValue(endValue);
      return;
    }

    const startValue = displayRef.current;
    const steps = 60;
    const stepDuration = 800 / steps; // 800ms total
    let currentStep = 0;

    const timer = setInterval(() => {
      currentStep++;
      const next =
        currentStep >= steps
          ? endValue
          : startValue + ((endValue - startValue) * currentStep) / steps;
      displayRef.current = next;
      setDisplayValue(next);
      if (currentStep >= steps) clearInterval(timer);
    }, stepDuration);

    return () => clearInterval(timer);
  }, [value, max, animated]);

  const percentage = Math.min((displayValue / max) * 100, 100);

  const getColorClasses = () => {
    switch (color) {
      case "green":
        return "bg-green-600";
      case "yellow":
        return "bg-yellow-500";
      case "red":
        return "bg-red-600";
      default:
        return "bg-blue-600";
    }
  };

  const getSizeClasses = () => {
    switch (size) {
      case "sm":
        return "h-1";
      case "lg":
        return "h-4";
      default:
        return "h-2";
    }
  };

  return (
    <div className={`w-full ${className}`}>
      {showLabel && (
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">Progress</span>
          <span className="text-muted-foreground">
            {indeterminate ? "Processing..." : `${Math.round(percentage)}%`}
          </span>
        </div>
      )}

      <div
        role="progressbar"
        aria-label="Progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : Math.round(percentage)}
        className={`w-full bg-gray-200 rounded-full ${getSizeClasses()}`}
      >
        {indeterminate ? (
          <div
            className={`
            ${getSizeClasses()} rounded-full ${getColorClasses()}
            animate-pulse w-1/3
            ${animated ? "transition-all duration-1000 ease-in-out" : ""}
          `}
          >
            <div className="h-full bg-white opacity-30 rounded-full animate-ping"></div>
          </div>
        ) : (
          <div
            className={`
              ${getSizeClasses()} rounded-full ${getColorClasses()}
              ${animated ? "transition-all duration-500 ease-out" : ""}
              flex items-center justify-end pr-1
            `}
            style={{ width: `${Math.max(percentage, 2)}%` }}
          >
            {size === "lg" && percentage > 15 && (
              <span className="text-xs text-white font-medium">
                {Math.round(percentage)}%
              </span>
            )}
          </div>
        )}
      </div>

      {indeterminate && (
        <div className="text-xs text-muted-foreground mt-1 text-center">
          <span className="animate-pulse">Processing your repository...</span>
        </div>
      )}
    </div>
  );
}
