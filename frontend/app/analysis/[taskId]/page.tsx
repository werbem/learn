"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProgressTracker } from "@/components/progress-tracker";
import { createReport, getProgress } from "@/lib/api";
import { saveToHistory } from "@/lib/utils";
import type { AnalysisInput, PhaseRecord } from "@/types";
import { PHASE_LABELS, PHASE_ORDER } from "@/types";

const POLL_INTERVAL = 800;
const MAX_WAIT_SECONDS = 300;

type PageState =
  | { type: "loading"; taskId: string }
  | { type: "creating"; taskId: string; payload: AnalysisInput }
  | { type: "polling"; taskId: string; serverTaskId: string }
  | { type: "completed"; taskId: string }
  | { type: "error"; message: string }
  | { type: "timeout" };

export default function AnalysisProgressPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const router = useRouter();
  const [state, setState] = useState<PageState>({ type: "loading", taskId: "" });
  const [phase, setPhase] = useState("");
  const [progress, setProgress] = useState(0);
  const [phaseHistory, setPhaseHistory] = useState<PhaseRecord[]>([]);
  const startTime = useRef(Date.now());

  // Resolve taskId from params and check for pending task
  useEffect(() => {
    params.then((p) => {
      const taskId = p.taskId;
      // Check sessionStorage for a pending task created by the form
      const raw = sessionStorage.getItem("pending_analysis");
      if (raw) {
        try {
          const pending = JSON.parse(raw);
          if (pending.clientTaskId === taskId && pending.payload) {
            setState({ type: "creating", taskId, payload: pending.payload });
            return;
          }
        } catch {
          // ignore invalid JSON
        }
      }
      // Normal flow: task already exists in backend
      setState({ type: "polling", taskId, serverTaskId: taskId });
    }).catch(() => router.push("/"));
  }, [params, router]);

  // Handle the "creating" phase — POST to backend, then start polling
  useEffect(() => {
    if (state.type !== "creating") return;

    const doCreate = async () => {
      try {
        const result = await createReport(state.payload);
        saveToHistory({
          taskId: result.task_id,
          ourCompany: state.payload.our_company,
          competitorCompany: state.payload.competitor_company,
          product: state.payload.product,
          objective: state.payload.objective,
        });
        // Clear pending data
        sessionStorage.removeItem("pending_analysis");
        // Task is complete (backend runs sync) — start polling with server task_id
        setState({ type: "polling", taskId: state.taskId, serverTaskId: result.task_id });
      } catch (err) {
        const msg = err instanceof Error ? err.message : "创建分析任务失败";
        setState({ type: "error", message: msg });
      }
    };
    doCreate();
  }, [state, router]);

  // Poll progress
  useEffect(() => {
    if (state.type !== "polling") return;

    const interval = setInterval(async () => {
      try {
        const data = await getProgress(state.serverTaskId);
        const elapsed = (Date.now() - startTime.current) / 1000;
        if (elapsed > MAX_WAIT_SECONDS) {
          setState({ type: "timeout" });
          clearInterval(interval);
          return;
        }

        setPhase(data.current_agent || data.status);
        setProgress(data.progress);
        setPhaseHistory(data.phase_history || []);

        if (data.status === "completed") {
          clearInterval(interval);
          await new Promise((r) => setTimeout(r, 500));
          setState({ type: "completed", taskId: state.serverTaskId });
          router.push(`/report/${state.serverTaskId}`);
        } else if (data.status === "failed" || data.status === "review_failed") {
          clearInterval(interval);
          setState({ type: "error", message: data.error_info || "分析任务失败" });
        } else if (data.status === "need_more_research") {
          clearInterval(interval);
          setState({ type: "error", message: "证据不足，需要补充更多信息后重新分析" });
        }
      } catch {
        // Task may not be ready yet — keep polling
      }
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [state, router]);

  const handleCancel = useCallback(() => {
    sessionStorage.removeItem("pending_analysis");
    router.push("/");
  }, [router]);

  // ── Render ──

  if (state.type === "loading") {
    return (
      <div className="flex justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (state.type === "creating") {
    return (
      <div className="max-w-2xl mx-auto space-y-8 py-4">
        <div className="text-center space-y-4">
          <div className="flex justify-center gap-1.5">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-3 w-3 rounded-full bg-primary animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
          <h1 className="text-2xl font-bold">正在创建分析任务</h1>
          <p className="text-muted-foreground">
            AI 正在准备分析引擎，即将开始情报收集...
          </p>
        </div>

        <Card className="p-8">
          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm">
              <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
              <span>验证输入参数</span>
            </div>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-muted-foreground/30" />
              <span>制定研究计划</span>
            </div>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-muted-foreground/30" />
              <span>跨源证据采集</span>
            </div>
          </div>
        </Card>

        <div className="text-center">
          <Button variant="ghost" onClick={handleCancel}>
            取消返回首页
          </Button>
        </div>
      </div>
    );
  }

  if (state.type === "timeout") {
    return (
      <div className="max-w-lg mx-auto text-center space-y-4 py-12">
        <div className="text-4xl">⏰</div>
        <h2 className="text-xl font-semibold">分析超时</h2>
        <p className="text-muted-foreground">分析超过 5 分钟仍未完成，请稍后重试</p>
        <div className="flex justify-center gap-3">
          <Button variant="outline" onClick={handleCancel}>返回首页</Button>
          <Button onClick={() => window.location.reload()}>重试</Button>
        </div>
      </div>
    );
  }

  if (state.type === "error") {
    return (
      <div className="max-w-lg mx-auto text-center space-y-4 py-12">
        <div className="text-4xl">❌</div>
        <h2 className="text-xl font-semibold">分析失败</h2>
        <p className="text-muted-foreground">{state.message}</p>
        <Button variant="outline" onClick={handleCancel}>返回首页</Button>
      </div>
    );
  }

  // state.type === "polling" — progress tracking
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
        <Button variant="ghost" onClick={handleCancel}>取消返回首页</Button>
      </div>
    </div>
  );
}
