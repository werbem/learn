"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProgressTracker } from "@/components/progress-tracker";
import { getProgress } from "@/lib/api";
import type { PhaseRecord } from "@/types";

const POLL_INTERVAL = 800;
const MAX_WAIT_SECONDS = 300; // 5 min timeout

export default function AnalysisProgressPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const router = useRouter();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [phase, setPhase] = useState("initialized");
  const [progress, setProgress] = useState(0);
  const [phaseHistory, setPhaseHistory] = useState<PhaseRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [timeout, setTimeout_] = useState(false);
  const [polling, setPolling] = useState(true);
  const startTime = useRef(Date.now());

  // Resolve taskId from params
  useEffect(() => {
    params.then((p) => setTaskId(p.taskId)).catch(() => router.push("/"));
  }, [params, router]);

  // Poll progress
  useEffect(() => {
    if (!taskId || !polling) return;

    const interval = setInterval(async () => {
      try {
        const data = await getProgress(taskId);
        setPhase(data.current_agent || data.status);
        setProgress(data.progress);
        setPhaseHistory(data.phase_history || []);

        const elapsed = (Date.now() - startTime.current) / 1000;
        if (elapsed > MAX_WAIT_SECONDS) {
          setTimeout_(true);
          setPolling(false);
          clearInterval(interval);
          return;
        }

        // Completed or terminal states
        if (
          data.status === "completed" ||
          data.status === "failed" ||
          data.status === "need_more_research" ||
          data.status === "review_failed"
        ) {
          setPolling(false);
          clearInterval(interval);

          if (data.status === "completed") {
            // Short delay before redirect
            await new Promise((r) => setTimeout(r, 500));
            router.push(`/report/${taskId}`);
          } else if (data.status === "failed" || data.status === "review_failed") {
            setError(data.error_info || "分析任务失败");
          } else if (data.status === "need_more_research") {
            setError("证据不足，需要补充更多信息后重新分析");
          }
        }
      } catch {
        // Task may not be ready yet — keep polling
      }
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [taskId, polling, router]);

  const handleCancel = () => {
    setPolling(false);
    router.push("/");
  };

  if (!taskId) {
    return (
      <div className="flex justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (timeout) {
    return (
      <div className="max-w-lg mx-auto text-center space-y-4 py-12">
        <div className="text-4xl">⏰</div>
        <h2 className="text-xl font-semibold">分析超时</h2>
        <p className="text-muted-foreground">
          分析超过 5 分钟仍未完成，请稍后重试
        </p>
        <div className="flex justify-center gap-3">
          <Button variant="outline" onClick={handleCancel}>
            返回首页
          </Button>
          <Button onClick={() => window.location.reload()}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto text-center space-y-4 py-12">
        <div className="text-4xl">❌</div>
        <h2 className="text-xl font-semibold">分析失败</h2>
        <p className="text-muted-foreground">{error}</p>
        <Button variant="outline" onClick={handleCancel}>
          返回首页
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8 py-4">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-bold">正在分析中</h1>
        <p className="text-muted-foreground text-sm">
          AI 正在收集情报并进行深度分析，请稍候...
        </p>
      </div>

      <Card className="p-6">
        <ProgressTracker
          currentPhase={phase}
          phaseHistory={phaseHistory}
          progress={progress}
        />
      </Card>

      <div className="text-center">
        <Button variant="ghost" onClick={handleCancel}>
          取消返回首页
        </Button>
      </div>
    </div>
  );
}
