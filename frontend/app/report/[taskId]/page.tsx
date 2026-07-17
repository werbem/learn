"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ReportViewer } from "@/components/report-viewer";
import { getReport, createReport } from "@/lib/api";
import { saveToHistory } from "@/lib/utils";
import type { AnalysisInput, ReportDetailResponse } from "@/types";

export default function ReportPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const router = useRouter();
  const resolvedParams = use(params);
  const taskId = resolvedParams.taskId;

  const [report, setReport] = useState<ReportDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [metaExpanded, setMetaExpanded] = useState(false);

  const fetchReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getReport(taskId);
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取报告失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [taskId]);

  const handleRegenerate = async () => {
    if (!report) return;
    setRegenerating(true);
    try {
      const result = await createReport({
        our_company: report.our_company,
        competitor_company: report.competitor_company,
        product: report.product,
        objective: report.objective as AnalysisInput["objective"],
      });
      saveToHistory({
        taskId: result.task_id,
        ourCompany: report.our_company,
        competitorCompany: report.competitor_company,
        product: report.product,
        objective: report.objective,
      });
      router.push(`/analysis/${result.task_id}`);
    } catch {
      setRegenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-muted-foreground">加载报告中...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto text-center space-y-4 py-12">
        <div className="text-4xl">❌</div>
        <h2 className="text-xl font-semibold">加载失败</h2>
        <p className="text-muted-foreground">{error}</p>
        <div className="flex justify-center gap-3">
          <Button variant="outline" onClick={() => router.push("/")}>
            返回首页
          </Button>
          <Button onClick={fetchReport}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="max-w-lg mx-auto text-center space-y-4 py-12">
        <div className="text-4xl">📄</div>
        <h2 className="text-xl font-semibold">报告不存在</h2>
        <p className="text-muted-foreground">该分析任务不存在或报告尚未生成</p>
        <Button variant="outline" onClick={() => router.push("/")}>
          返回首页
        </Button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Navigation bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
            <svg className="h-4 w-4 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5" /><polyline points="12 19 5 12 12 5" />
            </svg>
            返回首页
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRegenerate}
            disabled={regenerating}
          >
            {regenerating ? "重新生成中..." : "重新生成"}
          </Button>
        </div>
      </div>

      {/* Report header */}
      <Card>
        <CardContent className="p-6">
          <h1 className="text-2xl font-bold mb-4">竞品分析报告</h1>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <div className="text-muted-foreground mb-1">我方公司</div>
              <div className="font-medium">{report.our_company}</div>
            </div>
            <div>
              <div className="text-muted-foreground mb-1">竞品公司</div>
              <div className="font-medium">{report.competitor_company}</div>
            </div>
            <div>
              <div className="text-muted-foreground mb-1">分析产品</div>
              <div className="font-medium">{report.product}</div>
            </div>
            <div>
              <div className="text-muted-foreground mb-1">总字数</div>
              <div className="font-medium">{report.total_word_count?.toLocaleString() || "—"}</div>
            </div>
          </div>

          {/* Sections list */}
          {report.sections && report.sections.length > 0 && (
            <div className="mt-4">
              <button
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setMetaExpanded(!metaExpanded)}
              >
                {metaExpanded ? "收起" : "展开"}报告目录 ({report.sections.length} 章)
              </button>
              {metaExpanded && (
                <ol className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {report.sections.map((s, i) => (
                    <li key={s.order} className="flex items-center gap-2">
                      <span className="text-primary font-medium">{s.order}.</span>
                      <span>{s.title}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Report content */}
      <ReportViewer
        markdown={report.markdown}
        html={report.html}
        wordUrl={report.word_url}
      />
    </div>
  );
}
