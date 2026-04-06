import { redirect } from "next/navigation";

export default async function LegacyDashboardAccountPage() {
  redirect("/settings/personal/profile");
}
