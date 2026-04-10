import Team from "@/components/dashboard/Team";

export const dynamic = "force-dynamic";

export default async function TeamEmployeePage({
  params,
}: {
  params: Promise<{ employeeId: string }>;
}) {
  const { employeeId } = await params;

  return (
    <Team
      editingEmployeeId={employeeId}
      embeddedInShell
    />
  );
}
