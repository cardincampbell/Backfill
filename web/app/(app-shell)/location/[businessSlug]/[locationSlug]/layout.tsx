import LocationRouteResolver from "@/components/dashboard/LocationRouteResolver";

export default async function LocationLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ businessSlug: string; locationSlug: string }>;
}) {
  const { businessSlug, locationSlug } = await params;

  return (
    <>
      <LocationRouteResolver
        businessSlug={businessSlug}
        locationSlug={locationSlug}
      />
      {children}
    </>
  );
}
