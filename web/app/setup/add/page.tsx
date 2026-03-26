import Link from "next/link";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { SectionCard } from "@/components/section-card";
import { createLocation, createWorker } from "@/lib/server-api";

type SetupAddPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

async function submitManualSetup(formData: FormData) {
  "use server";

  const locationName = String(formData.get("location_name") ?? "").trim();
  const vertical = String(formData.get("vertical") ?? "restaurant").trim() || "restaurant";
  const workerName = String(formData.get("worker_name") ?? "").trim();
  const workerPhone = String(formData.get("worker_phone") ?? "").trim();

  if (!locationName) {
    redirect("/setup/add?status=error&message=Location+name+is+required");
  }

  if (!workerName || !workerPhone) {
    redirect("/setup/add?status=error&message=Initial+worker+name+and+phone+are+required");
  }

  try {
    const location = await createLocation({
      name: locationName,
      vertical,
      address: String(formData.get("address") ?? "").trim() || undefined,
      manager_name: String(formData.get("manager_name") ?? "").trim() || undefined,
      manager_phone: String(formData.get("manager_phone") ?? "").trim() || undefined,
      manager_email: String(formData.get("manager_email") ?? "").trim() || undefined,
      scheduling_platform: "backfill_native",
      onboarding_info: String(formData.get("onboarding_info") ?? "").trim() || undefined
    });

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
    });

    revalidatePath("/dashboard");
    redirect(`/setup/add?status=created&location_id=${location.id}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Setup failed";
    redirect(`/setup/add?status=error&message=${encodeURIComponent(message)}`);
  }
}

export default async function SetupAddPage({ searchParams }: SetupAddPageProps) {
  const params = searchParams ? await searchParams : {};
  const status = typeof params.status === "string" ? params.status : "";
  const message = typeof params.message === "string" ? decodeURIComponent(params.message) : "";
  const locationId = typeof params.location_id === "string" ? params.location_id : "";

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Manual Setup</span>
        <h1>Add the location and team by hand when nothing else exists.</h1>
        <p>
          This is the Native Lite path for operators with no scheduler and no clean export. Keep the setup
          narrow: primary contact details, worker roster, roles, and the minimum notes needed to run coverage.
        </p>
      </div>

      <div className="three-up">
        <SectionCard title="Location basics">
          <p>Name, address, business vertical, primary contact, and any arrival or reporting notes.</p>
        </SectionCard>
        <SectionCard title="Worker roster">
          <p>Add workers with phone, role, certifications, and preferred channel so the system can reach the right people fast.</p>
        </SectionCard>
        <SectionCard title="Go live">
          <p>Once consent is collected, workers can call or text 1-800-BACKFILL and the coverage workflow runs from the ledger.</p>
        </SectionCard>
      </div>

      {status === "created" ? (
        <section className="section">
          <div className="callout success-callout">
            <h3>Manual setup saved</h3>
            <p>
              Location and initial worker created in Native Lite. Location ID: <strong>{locationId}</strong>.
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
            <p className="muted">This writes directly into the existing Native Lite location and worker APIs.</p>
          </div>
        </div>
        <form className="setup-form" action={submitManualSetup}>
          <div className="form-grid">
            <label className="field">
              <span>Location name</span>
              <input name="location_name" placeholder="Coastal Grill Downtown" required />
            </label>
            <label className="field">
              <span>Vertical</span>
              <select name="vertical" defaultValue="restaurant">
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
              <input name="address" placeholder="123 Main St, Los Angeles, CA" />
            </label>
            <label className="field">
              <span>Primary contact name</span>
              <input name="manager_name" placeholder="Jordan Lee" />
            </label>
            <label className="field">
              <span>Primary contact phone</span>
              <input name="manager_phone" placeholder="+13105550100" />
            </label>
            <label className="field">
              <span>Primary contact email</span>
              <input name="manager_email" placeholder="mike@coastalgrill.com" />
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
            <p>Conversation should start onboarding, not replace structured data entry. Use integration or CSV when available.</p>
          </div>
          <div className="callout">
            <h3>Have structured data after all?</h3>
            <p>
              Move to <Link className="text-link" href="/setup/connect">scheduler connect</Link> or{" "}
              <Link className="text-link" href="/setup/upload">CSV upload</Link>.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
