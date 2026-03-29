import Link from "next/link";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { SectionCard } from "@/components/section-card";
import { createLocation, createWorker, getLocation, updateLocation } from "@/lib/server-api";

type SetupAddPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

async function submitManualSetup(formData: FormData) {
  "use server";

  const existingLocationId = Number(formData.get("location_id") || 0) || undefined;
  const setupToken = String(formData.get("setup_token") ?? "").trim() || undefined;
  const locationName = String(formData.get("location_name") ?? "").trim();
  const organizationName = String(formData.get("organization_name") ?? "").trim();
  const vertical = String(formData.get("vertical") ?? "restaurant").trim() || "restaurant";
  const workerName = String(formData.get("worker_name") ?? "").trim();
  const workerPhone = String(formData.get("worker_phone") ?? "").trim();

  if (!locationName) {
    redirect(`/setup/add?status=error&message=Location+name+is+required${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`);
  }

  if (!workerName || !workerPhone) {
    redirect(`/setup/add?status=error&message=Initial+worker+name+and+phone+are+required${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`);
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

    const role = String(formData.get("worker_role") ?? "").trim();
    const certifications = String(formData.get("worker_certifications") ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

    await createWorker({
      name: workerName,
      phone: workerPhone,
      email: String(formData.get("worker_email") ?? "").trim() || undefined,
      location_id: location.id,
      preferred_channel: String(formData.get("worker_channel") ?? "sms").trim() || "sms",
      roles: role ? [role] : [],
      certifications,
      source: "csv_import"
    }, { setupToken });

    revalidatePath("/dashboard");
    redirect(`/setup/add?status=created&location_id=${location.id}${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Setup failed";
    redirect(`/setup/add?status=error&message=${encodeURIComponent(message)}${setupToken ? `&setup_token=${encodeURIComponent(setupToken)}` : ""}`);
  }
}

export default async function SetupAddPage({ searchParams }: SetupAddPageProps) {
  const params = searchParams ? await searchParams : {};
  const setupToken = typeof params.setup_token === "string" ? params.setup_token : "";
  const resumeLocationId = typeof params.location_id === "string" ? Number(params.location_id) || 0 : 0;
  const status = typeof params.status === "string" ? params.status : "";
  const message = typeof params.message === "string" ? decodeURIComponent(params.message) : "";
  const locationId = typeof params.location_id === "string" ? params.location_id : "";
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
        <span className="eyebrow">Manual Fallback</span>
        <h1>Add the location and first team members by hand when no CSV exists.</h1>
        <p>
          Use this only when the operator has no scheduler and no clean export yet. Backfill Shifts should
          normally start from the CSV path so the schedule layer can be activated faster.
        </p>
      </div>

      <div className="three-up">
          <SectionCard title="Location basics">
            <p>Name, address, business vertical, primary contact, and any arrival or reporting notes.</p>
          </SectionCard>
          <SectionCard title="Worker roster">
            <p>Add workers with phone, role, certifications, and preferred channel so the system can reach the right people fast.</p>
          </SectionCard>
          <SectionCard title="Bridge into Backfill Shifts">
            <p>Once the initial roster is in, move into the CSV path as soon as possible so Backfill becomes the schedule and coverage layer.</p>
          </SectionCard>
        </div>

      {status === "created" ? (
        <section className="section">
          <div className="callout success-callout">
            <h3>Manual setup saved</h3>
            <p>
              Location and initial worker created. Location ID: <strong>{locationId}</strong>.
              Review it in the <Link className="text-link" href="/dashboard">dashboard</Link>.
            </p>
          </div>
        </section>
      ) : null}

      {status === "error" ? (
        <section className="section">
          <div className="callout error-callout">
            <h3>Setup could not be saved</h3>
            <p>{message || "Check the form values and try again."}</p>
          </div>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Create a location and first worker</h2>
            <p className="muted">This is the fallback path when Backfill Shifts cannot start from a CSV yet.</p>
          </div>
        </div>
        <form className="setup-form" action={submitManualSetup}>
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
              <span>Initial worker name</span>
              <input name="worker_name" placeholder="Devon Carter" required />
            </label>
            <label className="field">
              <span>Initial worker phone</span>
              <input name="worker_phone" placeholder="+13105550123" required />
            </label>
            <label className="field">
              <span>Initial worker email</span>
              <input name="worker_email" placeholder="devon@example.com" />
            </label>
            <label className="field">
              <span>Primary role</span>
              <input name="worker_role" placeholder="line_cook" />
            </label>
            <label className="field">
              <span>Preferred channel</span>
              <select name="worker_channel" defaultValue="sms">
                <option value="sms">sms</option>
                <option value="voice">voice</option>
                <option value="both">both</option>
              </select>
            </label>
            <label className="field field-span-2">
              <span>Certifications</span>
              <input name="worker_certifications" placeholder="food_handler_card, servsafe" />
            </label>
            <label className="field field-span-2">
              <span>Onboarding notes</span>
              <textarea
                name="onboarding_info"
                rows={4}
                defaultValue={defaultOnboardingInfo}
                placeholder="Parking, dress code, who to report to, special arrival notes."
              />
            </label>
          </div>
          <button className="button" type="submit">Create in Native Lite</button>
        </form>
      </section>

      <section className="section">
        <div className="two-up">
          <div className="callout">
            <h3>Use this only when needed</h3>
            <p>Conversation should collect the context. Use integration or the Backfill Shifts CSV path whenever possible.</p>
          </div>
          <div className="callout">
            <h3>Have structured data after all?</h3>
            <p>
              Move to <Link className="text-link" href={`/setup/connect${linkSuffix}`}>scheduler connect</Link> or{" "}
              <Link className="text-link" href={`/setup/upload${linkSuffix}`}>Backfill Shifts CSV setup</Link>.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
