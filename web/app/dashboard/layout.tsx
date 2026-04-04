import { requireAppSession } from "@/lib/require-app-session";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAppSession();
  return children;
}
