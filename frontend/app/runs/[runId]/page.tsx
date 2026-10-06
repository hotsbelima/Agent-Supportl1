import { RunRouter } from "@/components/run-router";

type RunPageProps = {
  params: Promise<{ runId: string }>;
};

export default async function RunPage({ params }: RunPageProps) {
  const { runId } = await params;
  return <RunRouter key={runId} runId={runId} />;
}
