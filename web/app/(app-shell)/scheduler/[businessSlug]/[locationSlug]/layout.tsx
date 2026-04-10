import SchedulerRouteResolver from "@/components/dashboard/SchedulerRouteResolver";

export default async function SchedulerLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ businessSlug: string; locationSlug: string }>;
}) {
  const { businessSlug, locationSlug } = await params;

  return (
    <>
      <SchedulerRouteResolver
        businessSlug={businessSlug}
        locationSlug={locationSlug}
      />
      {children}
    </>
  );
}
