import Link from "next/link";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { SectionCard } from "@/components/section-card";
import { connectAndSyncLocation, createLocation } from "@/lib/server-api";

const platforms = [
  {
    name: "7shifts",
    value: "7shifts",
    body: "Preferred path when the customer location already runs 7shifts. Connect once, import roster and schedule, and keep Backfill Native as the fill ledger."
  },
  {
    name: "Deputy",
    value: "deputy",
    body: "Same model as 7shifts: connect the source system, ingest the roster, and orchestrate fills on top."
  },
  {
    name: "When I Work",
    value: "wheniwork",
    body: "Connect first, then determine whether the account supports write-back. If not, Backfill runs the coverage workflow in companion mode."
  },
  {
    name: "Homebase",
    value: "homebase",
    body: "Read-only companion path. Pull roster and schedule context in, but keep the fill workflow in Backfill Native Lite."
  }
];

const platformConfig: Record<string, { headline: string; idLabel: string; idHint: string; mode: string }> = {
  "7shifts": {
    headline: "Use 7shifts for roster and schedule context while Backfill Native remains the operational source of truth for fills.",
    idLabel: "7shifts company ID",
    idHint: "Required for sync in the current adapter.",
    mode: "Companion core, paid write-back optional"
  },
  deputy: {
    headline: "Use Deputy for roster and schedule context while Backfill Native remains the operational source of truth for fills.",
    idLabel: "Deputy install URL",
    idHint: "The current adapter expects the per-location Deputy installation URL.",
    mode: "Companion core, paid write-back optional"
  },
  wheniwork: {
    headline: "Connect When I Work first, then decide whether write-back is available or companion mode is required.",
    idLabel: "When I Work account ID",
    idHint: "Required for roster/schedule reads in the current adapter.",
    mode: "Conditional write / companion"
  },
  homebase: {
    headline: "Homebase is companion mode. Pull context in, but keep fill state in Backfill.",
    idLabel: "Homebase location reference",
    idHint: "Optional for now. The current adapter mainly relies on the shared API key.",
    mode: "Read-only companion"
  }
};

type SetupConnectPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

async function submitConnectSetup(formData: FormData) {
  "use server";

  const locationName = String(formData.get("location_name") ?? "").trim();
  const vertical = String(formData.get("vertical") ?? "restaurant").trim() || "restaurant";
  const platform = String(formData.get("platform") ?? "").trim();

  if (!locationName) {
    redirect("/setup/connect?status=error&message=Location+name+is+required");
  }

  if (!platform) {
    redirect("/setup/connect?status=error&message=Platform+selection+is+required");
  }

  try {
    const location = await createLocation({
      name: locationName,
      vertical,
      address: String(formData.get("address") ?? "").trim() || undefined,
      manager_name: String(formData.get("manager_name") ?? "").trim() || undefined,
      manager_phone: String(formData.get("manager_phone") ?? "").trim() || undefined,
      manager_email: String(formData.get("manager_email") ?? "").trim() || undefined,
      scheduling_platform: platform,
      integration_status: "pending_setup",
      scheduling_platform_id: String(formData.get("scheduling_platform_id") ?? "").trim() || undefined,
      writeback_enabled: formData.get("writeback_enabled") === "on",
      writeback_subscription_tier: formData.get("writeback_enabled") === "on" ? "premium" : "core",
      onboarding_info: String(formData.get("onboarding_info") ?? "").trim() || undefined
    });

    const syncResult = await connectAndSyncLocation(location.id);

    revalidatePath("/dashboard");
    redirect(
      `/setup/connect?status=created&location_id=${location.id}&platform=${encodeURIComponent(platform)}&sync=${encodeURIComponent(syncResult.status)}`
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Connect setup failed";
    redirect(`/setup/connect?status=error&message=${encodeURIComponent(message)}`);
  }
}

export default async function SetupConnectPage({ searchParams }: SetupConnectPageProps) {
  const params = searchParams ? await searchParams : {};
  const selectedPlatform = typeof params.platform === "string" ? params.platform : null;
  const status = typeof params.status === "string" ? params.status : "";
  const message = typeof params.message === "string" ? decodeURIComponent(params.message) : "";
  const locationId = typeof params.location_id === "string" ? params.location_id : "";
  const syncStatus = typeof params.sync === "string" ? decodeURIComponent(params.sync) : "";
  const config = platformConfig[selectedPlatform ?? "7shifts"] ?? platformConfig["7shifts"];

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Location Setup</span>
        <h1>Connect the scheduler first when one exists.</h1>
        <p>
          The phone call captures intent. This page handles structured setup for locations that already
          manage schedules in software. Current supported integrations are strongest for shift-based operators.
        </p>
      </div>

      {status === "created" ? (
        <section className="section">
          <div className="callout success-callout">
            <h3>Integration path saved</h3>
            <p>
              Location ID <strong>{locationId}</strong> created with source platform{" "}
              <strong>{selectedPlatform}</strong>. Sync status: <strong>{syncStatus || "created"}</strong>. Review the configuration in the{" "}
              <Link className="text-link" href="/dashboard">dashboard</Link>.
            </p>
          </div>
        </section>
      ) : null}

      {status === "error" ? (
        <section className="section">
          <div className="callout error-callout">
            <h3>Connect setup failed</h3>
            <p>{message || "Check the values and try again."}</p>
          </div>
        </section>
      ) : null}

      {selectedPlatform ? (
        <section className="section">
          <div className="callout">
            <h3>Selected platform</h3>
            <p>
              Manager handoff is pre-routed to <strong>{selectedPlatform}</strong>. {config.headline}
            </p>
            <p><strong>{config.mode}</strong></p>
            <p className="muted">Default setup is read-only companion mode. Paid write-back can be enabled per location.</p>
          </div>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Create a connected location record</h2>
            <p className="muted">This stores scheduler context while keeping Native Lite as the fill execution ledger.</p>
          </div>
        </div>
        <form className="setup-form" action={submitConnectSetup}>
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
              <span>Platform</span>
              <select name="platform" defaultValue={selectedPlatform ?? "7shifts"}>
                <option value="7shifts">7shifts</option>
                <option value="deputy">deputy</option>
                <option value="wheniwork">wheniwork</option>
                <option value="homebase">homebase</option>
              </select>
            </label>
            <label className="field">
              <span>Address</span>
              <input name="address" placeholder="123 Main St, Los Angeles, CA" />
            </label>
            <label className="field">
              <span>{config.idLabel}</span>
              <input name="scheduling_platform_id" placeholder={config.idHint} />
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
            <label className="field field-span-2">
              <span>Onboarding notes</span>
              <textarea
                name="onboarding_info"
                rows={4}
                placeholder="Connection notes, reporting instructions, or any special context for the location."
              />
            </label>
            <label className="field field-span-2 checkbox-field">
              <span>Paid write-back</span>
              <label className="checkbox-inline">
                <input name="writeback_enabled" type="checkbox" />
                <span>Enable scheduler write-back for this location now.</span>
              </label>
            </label>
          </div>
          <button className="button" type="submit">Save connected location</button>
        </form>
      </section>

      <div className="feature-grid">
        {platforms.map((platform) => (
          <SectionCard key={platform.name} title={platform.name}>
            <p>{platform.body}</p>
            <p>
              <Link className="text-link" href={`/setup/connect?platform=${platform.value}`}>
                Open {platform.name} flow
              </Link>
            </p>
          </SectionCard>
        ))}
      </div>

      <section className="section">
        <div className="two-up">
          <div className="callout">
            <h3>Source-of-truth rule</h3>
            <p>Use the scheduler if Backfill can write to it. If not, Backfill holds the fill workflow state so nothing breaks.</p>
          </div>
          <div className="callout">
            <h3>No supported scheduler?</h3>
            <p>
              Use <Link className="text-link" href="/setup/upload">CSV upload</Link> or{" "}
              <Link className="text-link" href="/setup/add">manual team entry</Link>.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
