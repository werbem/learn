"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { createReport } from "@/lib/api";
import { saveToHistory } from "@/lib/utils";
import { OBJECTIVE_LABELS } from "@/types";
import type { AnalysisInput } from "@/types";

export function AnalysisForm() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<AnalysisInput>({
    our_company: "",
    competitor_company: "",
    product: "",
    objective: "go_to_market",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.our_company.trim() || !form.competitor_company.trim() || !form.product.trim()) {
      setError("请填写所有必填字段");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const result = await createReport(form);
      saveToHistory({
        taskId: result.task_id,
        ourCompany: form.our_company,
        competitorCompany: form.competitor_company,
        product: form.product,
        objective: form.objective,
      });
      router.push(`/analysis/${result.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建分析任务失败");
      setLoading(false);
    }
  };

  return (
    <Card className="max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="text-2xl">开始竞品分析</CardTitle>
        <CardDescription>填写以下信息，AI 将自动生成深度竞品分析报告</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">我方公司 *</label>
              <input
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="例：字节跳动"
                value={form.our_company}
                onChange={(e) => setForm({ ...form, our_company: e.target.value })}
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">竞品公司 *</label>
              <input
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="例：腾讯"
                value={form.competitor_company}
                onChange={(e) => setForm({ ...form, competitor_company: e.target.value })}
                disabled={loading}
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">分析产品 *</label>
            <input
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="例：抖音"
              value={form.product}
              onChange={(e) => setForm({ ...form, product: e.target.value })}
              disabled={loading}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">分析目标</label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.objective}
              onChange={(e) => setForm({ ...form, objective: e.target.value as AnalysisInput["objective"] })}
              disabled={loading}
            >
              {Object.entries(OBJECTIVE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          {error && (
            <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full h-10 text-base" disabled={loading}>
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                分析中...
              </span>
            ) : (
              "开始分析"
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
