"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getHistory } from "@/lib/utils";
import { formatDate } from "@/lib/utils";
import type { HistoryEntry } from "@/types";
import { OBJECTIVE_LABELS } from "@/types";

export function ReportHistory() {
  const router = useRouter();
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setHistory(getHistory());
  }, []);

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
            <button
              key={entry.taskId}
              className="w-full text-left p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
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
                {entry.product} · {OBJECTIVE_LABELS[entry.objective]?.split(" —")[0] || entry.objective}
              </div>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
