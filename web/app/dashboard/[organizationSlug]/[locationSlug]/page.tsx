import { redirect } from "next/navigation";

export default async function LegacyDashboardLocationSlugRoute() {
  redirect("/dashboard");
}
