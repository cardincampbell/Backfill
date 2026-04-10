import SchedulerRouteResolver from "@/components/dashboard/SchedulerRouteResolver";

export const dynamic = "force-dynamic";

export default async function SchedulerEditLocationPage({
  params,
}: {
  params: Promise<{ businessSlug: string; locationSlug: string }>;
}) {
  const { businessSlug, locationSlug } = await params;

  return (
    <SchedulerRouteResolver
      businessSlug={businessSlug}
      editingLocation
      locationSlug={locationSlug}
    />
  );
}
