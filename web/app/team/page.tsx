import Team from "@/components/source-dashboard/Team";
import { requireAppSession } from "@/lib/require-app-session";

export const dynamic = "force-dynamic";

export default async function TeamPage() {
  await requireAppSession();
  return <Team />;
}
