import DashboardLight from "@/components/dashboard/DashboardLight";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <DashboardLight embeddedInShell />
      {children}
    </>
  );
}
