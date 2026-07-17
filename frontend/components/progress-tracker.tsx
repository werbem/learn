"use client";

import { cn } from "@/lib/utils";
import { PHASE_LABELS, PHASE_ORDER } from "@/types";
import type { PhaseRecord } from "@/types";

const STEPS = [
  "validated",
  "planned",
  "researched",
  "compared",
  "strategized",
  "reported",
  "reviewed",
  "completed",
] as const;

interface ProgressTrackerProps {
  currentPhase: string;
  phaseHistory: PhaseRecord[];
  progress: number;
}

export function ProgressTracker({ currentPhase, phaseHistory, progress }: ProgressTrackerProps) {
  const currentIdx = PHASE_ORDER[currentPhase] ?? 0;

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm text-muted-foreground">
          <span>分析进度</span>
          <span>{Math.round(progress)}%</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-700 ease-out"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {STEPS.map((step, idx) => {
          const phase = phaseHistory.find((p) => p.phase === step);
          const isActive = currentPhase === step;
          const isPast = currentIdx > idx;
          const isFailed = phase?.status === "failed";
          const label = PHASE_LABELS[step] || step;

          return (
            <div
              key={step}
              className={cn(
                "flex items-center gap-3 rounded-lg p-3 transition-colors",
                isActive && "bg-primary/5 border border-primary/20",
                isPast && !isFailed && "text-muted-foreground",
                isFailed && "bg-destructive/5 border border-destructive/20"
              )}
            >
              {/* Icon */}
              <div
                className={cn(
                  "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium",
                  isPast && !isFailed && "bg-primary text-primary-foreground",
                  isActive && "bg-primary text-primary-foreground ring-2 ring-primary/30",
                  !isActive && !isPast && !isFailed && "bg-muted text-muted-foreground",
                  isFailed && "bg-destructive text-destructive-foreground"
                )}
              >
                {isPast && !isFailed ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : isFailed ? (
                  <span>!</span>
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {/* Label */}
              <span
                className={cn(
                  "flex-1 text-sm",
                  isActive && "font-semibold text-primary",
                  isFailed && "text-destructive"
                )}
              >
                {label}
                {isActive && !isFailed && (
                  <span className="ml-2 inline-flex">
                    <span className="animate-pulse-dot" style={{ animationDelay: "0ms" }}>.</span>
                    <span className="animate-pulse-dot" style={{ animationDelay: "200ms" }}>.</span>
                    <span className="animate-pulse-dot" style={{ animationDelay: "400ms" }}>.</span>
                  </span>
                )}
              </span>

              {/* Duration */}
              {phase && phase.duration_ms > 0 && (
                <span className="text-xs text-muted-foreground">
                  {(phase.duration_ms / 1000).toFixed(1)}s
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
