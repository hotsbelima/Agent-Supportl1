import { RunConsole } from "@/components/run-console";

type RunPageProps = {
  params: Promise<{ runId: string }>;
};

export default async function RunPage({ params }: RunPageProps) {
  const { runId } = await params;
  return <RunConsole runId={runId} />;
}
