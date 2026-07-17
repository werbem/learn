import { AnalysisForm } from "@/components/analysis-form";
import { ReportHistory } from "@/components/report-history";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div className="text-center space-y-2 py-4">
        <h1 className="text-3xl font-bold tracking-tight">
          AI 竞品分析助手
        </h1>
        <p className="text-muted-foreground max-w-lg mx-auto">
          输入公司和产品信息，AI 自动从互联网收集情报，生成深度竞品分析报告
        </p>
      </div>
      <AnalysisForm />
      <ReportHistory />
    </div>
  );
}
