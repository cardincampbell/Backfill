import Link from "next/link";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { SectionCard } from "@/components/section-card";
import { createLocation, getLocation, importWorkersCsvForLocation, updateLocation } from "@/lib/server-api";

type SetupUploadPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

async function submitCsvSetup(formData: FormData) {
  "use server";

  const existingLocationId = Number(formData.get("location_id") || 0) || undefined;
  const setupToken = String(formData.get("setup_token") ?? "").trim() || undefined;
  const locationName = String(formData.get("location_name") ?? "").trim();
  const organizationName = String(formData.get("organization_name") ?? "").trim();
  const vertical = String(formData.get("vertical") ?? "restaurant").trim() || "restaurant";
  const file = formData.get("roster_file");

  if (!locationName) {
    redirect(`/setup/upload?status=error&message=Location+name+is+required${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`);
  }
  if (!(file instanceof File) || !file.name) {
    redirect(`/setup/upload?status=error&message=CSV+file+is+required${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`);
  }

  try {
    const payload = {
      name: locationName,
      organization_name: organizationName || undefined,
      vertical,
      address: String(formData.get("address") ?? "").trim() || undefined,
      manager_name: String(formData.get("manager_name") ?? "").trim() || undefined,
      manager_phone: String(formData.get("manager_phone") ?? "").trim() || undefined,
      manager_email: String(formData.get("manager_email") ?? "").trim() || undefined,
      scheduling_platform: "backfill_native",
      onboarding_info: String(formData.get("onboarding_info") ?? "").trim() || undefined
    };
    const location = existingLocationId
      ? await updateLocation(existingLocationId, payload, { setupToken })
      : await createLocation(payload, { setupToken });

    const result = await importWorkersCsvForLocation(location.id, file, { setupToken });

    revalidatePath("/dashboard");
    redirect(
      `/setup/upload?status=created&location_id=${location.id}&created=${result.created}&skipped=${result.skipped}${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upload failed";
    redirect(`/setup/upload?status=error&message=${encodeURIComponent(message)}${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`);
  }
}

export default async function SetupUploadPage({ searchParams }: SetupUploadPageProps) {
  const params = searchParams ? await searchParams : {};
  const setupToken = typeof params.setup_token === "string" ? params.setup_token : "";
  const resumeLocationId = typeof params.location_id === "string" ? Number(params.location_id) || 0 : 0;
  const status = typeof params.status === "string" ? params.status : "";
  const locationId = typeof params.location_id === "string" ? params.location_id : "";
  const created = typeof params.created === "string" ? params.created : "";
  const skipped = typeof params.skipped === "string" ? params.skipped : "";
  const message = typeof params.message === "string" ? decodeURIComponent(params.message) : "";
  const existingLocation = resumeLocationId
    ? await getLocation(resumeLocationId, { setupToken: setupToken || undefined })
    : null;
  const defaultLocationName = typeof params.location_name === "string" ? decodeURIComponent(params.location_name) : existingLocation?.name ?? "";
  const defaultOrganizationName =
    typeof params.organization_name === "string"
      ? decodeURIComponent(params.organization_name)
      : existingLocation?.organization_name ?? "";
  const defaultVertical = typeof params.vertical === "string" ? params.vertical : existingLocation?.vertical ?? "restaurant";
  const defaultAddress = typeof params.address === "string" ? decodeURIComponent(params.address) : existingLocation?.address ?? "";
  const defaultManagerName =
    typeof params.manager_name === "string"
      ? decodeURIComponent(params.manager_name)
      : existingLocation?.manager_name ?? "";
  const defaultManagerPhone =
    typeof params.manager_phone === "string"
      ? decodeURIComponent(params.manager_phone)
      : existingLocation?.manager_phone ?? "";
  const defaultManagerEmail =
    typeof params.manager_email === "string"
      ? decodeURIComponent(params.manager_email)
      : existingLocation?.manager_email ?? "";
  const defaultOnboardingInfo =
    typeof params.onboarding_info === "string"
      ? decodeURIComponent(params.onboarding_info)
      : existingLocation?.onboarding_info ?? "";
  const linkParams = new URLSearchParams();
  if (resumeLocationId) {
    linkParams.set("location_id", String(resumeLocationId));
  }
  if (setupToken) {
    linkParams.set("setup_token", setupToken);
  }
  const linkSuffix = linkParams.toString() ? `?${linkParams.toString()}` : "";

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Backfill Shifts</span>
        <h1>Start Backfill Shifts by uploading the team roster.</h1>
        <p>
          This is the default setup path for operators without a connected scheduler. Import the team first,
          then use Backfill as the schedule and coverage layer instead of leaving the location hanging after onboarding.
        </p>
      </div>

      <div className="three-up">
        <SectionCard title="1. Import the team">
          <p>Start with names, phone numbers, roles, and certifications so Backfill can route coverage correctly.</p>
        </SectionCard>
        <SectionCard title="2. Set the operating record">
          <p>Confirm the location, primary contact phone, and the notes Backfill Shifts needs to run coverage cleanly.</p>
        </SectionCard>
        <SectionCard title="3. Go live">
          <p>Once consent is collected, this location can run schedule notifications, callouts, and open-shift outreach through Backfill.</p>
        </SectionCard>
      </div>

      {status === "created" ? (
        <section className="section">
          <div className="callout success-callout">
            <h3>Roster imported</h3>
            <p>
              Backfill Shifts is now started for location <strong>{locationId}</strong>. Imported <strong>{created}</strong> worker(s),
              skipped <strong>{skipped}</strong>. Review the location in the{" "}
              <Link className="text-link" href="/dashboard">dashboard</Link>.
            </p>
          </div>
        </section>
      ) : null}

      {status === "error" ? (
        <section className="section">
          <div className="callout error-callout">
            <h3>Upload could not be processed</h3>
            <p>{message || "Check the file and form values, then try again."}</p>
          </div>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Create the location and import the roster</h2>
            <p className="muted">Current supported columns: <code>name,phone,role,priority_rank</code>.</p>
          </div>
        </div>
        <form className="setup-form" action={submitCsvSetup}>
          {resumeLocationId ? <input name="location_id" type="hidden" value={resumeLocationId} /> : null}
          {setupToken ? <input name="setup_token" type="hidden" value={setupToken} /> : null}
          <div className="form-grid">
            <label className="field">
              <span>Business name</span>
              <input name="organization_name" placeholder="Coastal Hospitality Group" defaultValue={defaultOrganizationName} />
            </label>
            <label className="field">
              <span>Location name</span>
              <input name="location_name" placeholder="Coastal Grill Downtown" defaultValue={defaultLocationName} required />
            </label>
            <label className="field">
              <span>Vertical</span>
              <select name="vertical" defaultValue={defaultVertical}>
                <option value="restaurant">restaurant</option>
                <option value="healthcare">healthcare</option>
                <option value="warehouse">warehouse</option>
                <option value="retail">retail</option>
                <option value="hospitality">hospitality</option>
                <option value="other">other</option>
              </select>
            </label>
            <label className="field">
              <span>Address</span>
              <input name="address" placeholder="123 Main St, Los Angeles, CA" defaultValue={defaultAddress} />
            </label>
            <label className="field">
              <span>Primary contact name</span>
              <input name="manager_name" placeholder="Jordan Lee" defaultValue={defaultManagerName} />
            </label>
            <label className="field">
              <span>Primary contact phone</span>
              <input name="manager_phone" placeholder="+13105550100" defaultValue={defaultManagerPhone} />
            </label>
            <label className="field">
              <span>Primary contact email</span>
              <input name="manager_email" placeholder="mike@coastalgrill.com" defaultValue={defaultManagerEmail} />
            </label>
            <label className="field">
              <span>Backfill Shifts roster CSV</span>
              <input name="roster_file" type="file" accept=".csv" required />
            </label>
            <label className="field field-span-2">
              <span>Onboarding notes</span>
              <textarea
                name="onboarding_info"
                rows={4}
                defaultValue={defaultOnboardingInfo}
                placeholder="Parking, arrival instructions, dress code, or reporting notes."
              />
            </label>
          </div>
          <button className="button" type="submit">Start Backfill Shifts</button>
        </form>
      </section>

      <section className="section">
        <div className="callout">
          <h3>Manual fallback</h3>
          <p>
            If the location does not even have a spreadsheet, use{" "}
            <Link className="text-link" href={`/setup/add${linkSuffix}`}>manual team entry</Link>.
          </p>
        </div>
      </section>
    </main>
  );
}
