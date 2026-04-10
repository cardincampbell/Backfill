import DashboardLight from "@/components/dashboard/DashboardLight";

export const dynamic = "force-dynamic";

export default async function DashboardLocationEditPage({
  params,
}: {
  params: Promise<{ locationId: string }>;
}) {
  const { locationId } = await params;

  return (
    <DashboardLight
      editingLocationId={locationId}
      embeddedInShell
    />
  );
}
