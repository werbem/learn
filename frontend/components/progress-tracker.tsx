"use client";

import { cn } from "@/lib/utils";
import { PHASE_LABELS } from "@/types";
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
  activeStep: string;
  completedSteps: string[];
  phaseHistory: PhaseRecord[];
  progress: number;
  demoMode?: boolean;
}

export function ProgressTracker({ activeStep, completedSteps, phaseHistory, progress, demoMode }: ProgressTrackerProps) {
  // Determine which step is currently "active" (running)
  // activeStep comes directly from SSE "running" events
  // If empty and no completed steps, first step is pending

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      {demoMode && (
        <div className="flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-sm">
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" />
          </svg>
          <span className="font-medium">Demo 模式</span> — 固定案例 &quot;抖音 vs 快手&quot;，非真实 AI 分析
        </div>
      )}
      {/* Progress bar — phase-based, smooth */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm text-muted-foreground">
          <span>分析进度</span>
          <span>
            {completedSteps.length > 0
              ? `${Math.round(progress)}%`
              : "初始化中"}
          </span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-1000 ease-out"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {STEPS.map((step, idx) => {
          const phase = phaseHistory.find((p) => p.phase === step);
          const isCompleted = completedSteps.includes(step);
          const isActive = activeStep === step && !isCompleted;
          const isFailed = phase?.status === "failed";
          const label = PHASE_LABELS[step] || step;

          // Don't show "completed" step as a separate line if there are still active steps
          if (step === "completed" && activeStep && activeStep !== "completed") {
            return null;
          }

          return (
            <div
              key={step}
              className={cn(
                "flex items-center gap-3 rounded-lg p-3 transition-colors",
                isActive && "bg-primary/5 border border-primary/20",
                isFailed && "bg-destructive/5 border border-destructive/20"
              )}
            >
              {/* Icon */}
              <div
                className={cn(
                  "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium transition-all duration-300",
                  isCompleted && "bg-primary text-primary-foreground",
                  isActive && "bg-primary text-primary-foreground ring-2 ring-primary/30 scale-110",
                  !isActive && !isCompleted && !isFailed && "bg-muted text-muted-foreground",
                  isFailed && "bg-destructive text-destructive-foreground"
                )}
              >
                {isCompleted ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : isFailed ? (
                  <span>!</span>
                ) : isActive ? (
                  <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2a10 10 0 1 0 10 10" strokeLinecap="round" />
                  </svg>
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {/* Label */}
              <span
                className={cn(
                  "flex-1 text-sm transition-colors duration-300",
                  isActive && "font-semibold text-primary",
                  isCompleted && "text-foreground",
                  !isActive && !isCompleted && "text-muted-foreground",
                  isFailed && "text-destructive"
                )}
              >
                {label}
                {isActive && (
                  <span className="ml-2 inline-flex align-middle">
                    <span className="animate-pulse-dot inline-block w-1 h-1 rounded-full bg-primary" style={{ animationDelay: "0ms" }} />
                    <span className="animate-pulse-dot inline-block w-1 h-1 rounded-full bg-primary ml-0.5" style={{ animationDelay: "200ms" }} />
                    <span className="animate-pulse-dot inline-block w-1 h-1 rounded-full bg-primary ml-0.5" style={{ animationDelay: "400ms" }} />
                  </span>
                )}
              </span>

              {/* Duration */}
              {phase && phase.duration_ms > 0 && (
                <span className="text-xs text-muted-foreground font-mono">
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
