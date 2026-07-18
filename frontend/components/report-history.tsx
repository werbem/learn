"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getHistory, removeFromHistory, formatDate } from "@/lib/utils";
import { deleteReport } from "@/lib/api";
import { OBJECTIVE_LABELS } from "@/types";

interface HistoryEntry {
  taskId: string;
  ourCompany: string;
  competitorCompany: string;
  product: string;
  objective: string;
  createdAt: string;
}

export function ReportHistory() {
  const router = useRouter();
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setHistory(getHistory());
  }, []);

  const handleDelete = async (e: React.MouseEvent, taskId: string) => {
    e.stopPropagation();
    try { await deleteReport(taskId); } catch {}
    removeFromHistory(taskId);
    setHistory((prev) => prev.filter((h) => h.taskId !== taskId));
  };

  if (history.length === 0) return null;

  return (
    <Card className="max-w-2xl mx-auto mt-6">
      <CardHeader>
        <CardTitle className="text-lg">最近分析记录</CardTitle>
        <CardDescription>点击查看已完成的竞品分析报告</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {history.map((entry) => (
            <div key={entry.taskId} className="flex items-center gap-2">
              <button
                className="flex-1 text-left p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
                onClick={() => router.push(`/report/${entry.taskId}`)}
              >
                <div className="flex items-center justify-between">
                  <div className="font-medium text-sm">
                    {entry.ourCompany} vs {entry.competitorCompany}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {formatDate(entry.createdAt)}
                  </div>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {entry.product || "—"} · {OBJECTIVE_LABELS[entry.objective]?.split(" —")[0] || entry.objective || "—"}
                </div>
              </button>
              <button
                className="flex-shrink-0 p-2 rounded-lg border hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                onClick={(e) => handleDelete(e, entry.taskId)}
                title="删除记录"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
