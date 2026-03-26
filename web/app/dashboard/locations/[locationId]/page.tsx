import LocationDetailPage from "../../location-detail";

type LocationDetailPageRouteProps = {
  params: Promise<{ locationId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default function LocationDetailRoute(props: LocationDetailPageRouteProps) {
  return <LocationDetailPage {...props} />;
}
