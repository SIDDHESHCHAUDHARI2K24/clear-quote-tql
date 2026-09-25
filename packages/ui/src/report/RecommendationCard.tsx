import type { ReportRecommendationData } from "./types";

export interface RecommendationCardProps {
  recommendation: ReportRecommendationData;
}

export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  return (
    <section className="rounded-lg border border-sage-300 bg-sage-50 p-4">
      <h2 className="text-sm font-semibold text-sage-900">What we recommend</h2>
      <p className="mt-1 text-navy-900">{recommendation.text}</p>
      {recommendation.lo_note && (
        <p className="mt-2 border-t border-sage-300 pt-2 text-sm text-navy-900 italic">
          &ldquo;{recommendation.lo_note}&rdquo;
        </p>
      )}
    </section>
  );
}
