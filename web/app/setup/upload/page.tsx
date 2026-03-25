import Link from "next/link";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { SectionCard } from "@/components/section-card";
import { createRestaurant, importWorkersCsv } from "@/lib/server-api";

type SetupUploadPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

async function submitCsvSetup(formData: FormData) {
  "use server";

  const restaurantName = String(formData.get("restaurant_name") ?? "").trim();
  const file = formData.get("roster_file");

  if (!restaurantName) {
    redirect("/setup/upload?status=error&message=Restaurant+name+is+required");
  }
  if (!(file instanceof File) || !file.name) {
    redirect("/setup/upload?status=error&message=CSV+file+is+required");
  }

  try {
    const restaurant = await createRestaurant({
      name: restaurantName,
      address: String(formData.get("address") ?? "").trim() || undefined,
      manager_name: String(formData.get("manager_name") ?? "").trim() || undefined,
      manager_phone: String(formData.get("manager_phone") ?? "").trim() || undefined,
      manager_email: String(formData.get("manager_email") ?? "").trim() || undefined,
      scheduling_platform: "backfill_native",
      onboarding_info: String(formData.get("onboarding_info") ?? "").trim() || undefined
    });

    const result = await importWorkersCsv(restaurant.id, file);

    revalidatePath("/dashboard");
    redirect(
      `/setup/upload?status=created&restaurant_id=${restaurant.id}&created=${result.created}&skipped=${result.skipped}`
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upload failed";
    redirect(`/setup/upload?status=error&message=${encodeURIComponent(message)}`);
  }
}

export default async function SetupUploadPage({ searchParams }: SetupUploadPageProps) {
  const params = searchParams ? await searchParams : {};
  const status = typeof params.status === "string" ? params.status : "";
  const restaurantId = typeof params.restaurant_id === "string" ? params.restaurant_id : "";
  const created = typeof params.created === "string" ? params.created : "";
  const skipped = typeof params.skipped === "string" ? params.skipped : "";
  const message = typeof params.message === "string" ? decodeURIComponent(params.message) : "";

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">CSV Intake</span>
        <h1>Upload the team list when the data already exists.</h1>
        <p>
          This path is for restaurants without a supported writeable scheduler but with a spreadsheet or
          exported roster ready to go.
        </p>
      </div>

      <div className="three-up">
        <SectionCard title="1. Upload roster data">
          <p>Start with names, phone numbers, roles, and certifications. Keep the import small and operational.</p>
        </SectionCard>
        <SectionCard title="2. Verify manager contacts">
          <p>Confirm the location, manager phone, and any onboarding notes the coverage engine needs later.</p>
        </SectionCard>
        <SectionCard title="3. Collect worker consent">
          <p>After import, text workers the Backfill disclosure so outreach consent is logged before live coverage starts.</p>
        </SectionCard>
      </div>

      {status === "created" ? (
        <section className="section">
          <div className="callout success-callout">
            <h3>Roster imported</h3>
            <p>
              Restaurant ID <strong>{restaurantId}</strong> created. Imported <strong>{created}</strong> worker(s),
              skipped <strong>{skipped}</strong>. Review the results in the{" "}
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
            <h2>Create the restaurant and import a CSV</h2>
            <p className="muted">Expected CSV columns: <code>name,phone,role,priority_rank</code>.</p>
          </div>
        </div>
        <form className="setup-form" action={submitCsvSetup}>
          <div className="form-grid">
            <label className="field">
              <span>Restaurant name</span>
              <input name="restaurant_name" placeholder="Coastal Grill" required />
            </label>
            <label className="field">
              <span>Address</span>
              <input name="address" placeholder="123 Main St, Los Angeles, CA" />
            </label>
            <label className="field">
              <span>Manager name</span>
              <input name="manager_name" placeholder="Chef Mike" />
            </label>
            <label className="field">
              <span>Manager phone</span>
              <input name="manager_phone" placeholder="+13105550100" />
            </label>
            <label className="field">
              <span>Manager email</span>
              <input name="manager_email" placeholder="mike@coastalgrill.com" />
            </label>
            <label className="field">
              <span>Roster CSV</span>
              <input name="roster_file" type="file" accept=".csv" required />
            </label>
            <label className="field field-span-2">
              <span>Onboarding notes</span>
              <textarea
                name="onboarding_info"
                rows={4}
                placeholder="Parking, arrival instructions, dress code, or reporting notes."
              />
            </label>
          </div>
          <button className="button" type="submit">Create restaurant and import roster</button>
        </form>
      </section>

      <section className="section">
        <div className="callout">
          <h3>Fallback path</h3>
          <p>
            If the restaurant does not even have a spreadsheet, use{" "}
            <Link className="text-link" href="/setup/add">manual team entry</Link>.
          </p>
        </div>
      </section>
    </main>
  );
}
