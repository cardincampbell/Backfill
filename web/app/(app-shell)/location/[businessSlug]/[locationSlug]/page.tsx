import LocationRouteResolver from "@/components/dashboard/LocationRouteResolver";

export const dynamic = "force-dynamic";

export default async function LocationPage({
  params,
}: {
  params: Promise<{ businessSlug: string; locationSlug: string }>;
}) {
  const { businessSlug, locationSlug } = await params;
  return (
    <LocationRouteResolver
      businessSlug={businessSlug}
      locationSlug={locationSlug}
    />
  );
}
