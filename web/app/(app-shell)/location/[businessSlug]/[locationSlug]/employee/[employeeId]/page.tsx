import LocationRouteResolver from "@/components/dashboard/LocationRouteResolver";

export const dynamic = "force-dynamic";

export default async function LocationEmployeePage({
  params,
}: {
  params: Promise<{
    businessSlug: string;
    employeeId: string;
    locationSlug: string;
  }>;
}) {
  const { businessSlug, employeeId, locationSlug } = await params;

  return (
    <LocationRouteResolver
      businessSlug={businessSlug}
      editingEmployeeId={employeeId}
      locationSlug={locationSlug}
    />
  );
}
