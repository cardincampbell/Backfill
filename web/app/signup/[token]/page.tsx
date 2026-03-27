import Link from "next/link";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { SectionCard } from "@/components/section-card";
import { completeSignupSession, getSignupSession } from "@/lib/server-api";

type SignupPageProps = {
  params: Promise<{ token: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

async function submitSignup(token: string, formData: FormData) {
  "use server";

  const businessName = String(formData.get("business_name") ?? "").trim();
  const locationName = String(formData.get("location_name") ?? "").trim();
  const contactPhone = String(formData.get("contact_phone") ?? "").trim();

  if (!businessName) {
    redirect(`/signup/${token}?status=error&message=Business+name+is+required`);
  }
  if (!locationName) {
    redirect(`/signup/${token}?status=error&message=Location+name+is+required`);
  }
  if (!contactPhone) {
    redirect(`/signup/${token}?status=error&message=Primary+contact+phone+is+required`);
  }

  try {
    const result = await completeSignupSession(token, {
      business_name: businessName,
      location_name: locationName,
      contact_name: String(formData.get("contact_name") ?? "").trim() || undefined,
      contact_phone: contactPhone,
      contact_email: String(formData.get("contact_email") ?? "").trim() || undefined,
      vertical: String(formData.get("vertical") ?? "other").trim() || "other",
      location_count: Number(formData.get("location_count") || 0) || undefined,
      employee_count: Number(formData.get("employee_count") || 0) || undefined,
      address: String(formData.get("address") ?? "").trim() || undefined,
      pain_point_summary: String(formData.get("pain_point_summary") ?? "").trim() || undefined,
      urgency: String(formData.get("urgency") ?? "").trim() || undefined,
      notes: String(formData.get("notes") ?? "").trim() || undefined,
      setup_kind: String(formData.get("setup_kind") ?? "manual_form").trim() || "manual_form",
      scheduling_platform: String(formData.get("scheduling_platform") ?? "backfill_native").trim() || "backfill_native"
    });
    revalidatePath("/dashboard");
    redirect(
      `/signup/${token}?status=completed&location_id=${result.location.id}&next=${encodeURIComponent(result.next_path)}`
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Signup could not be completed";
    redirect(`/signup/${token}?status=error&message=${encodeURIComponent(message)}`);
  }
}

export default async function SignupPage({ params, searchParams }: SignupPageProps) {
  const { token } = await params;
  const query = searchParams ? await searchParams : {};
  const status = typeof query.status === "string" ? query.status : "";
  const message = typeof query.message === "string" ? decodeURIComponent(query.message) : "";
  const nextPath = typeof query.next === "string" ? decodeURIComponent(query.next) : "";
  const locationId = typeof query.location_id === "string" ? query.location_id : "";

  let session: Awaited<ReturnType<typeof getSignupSession>>;
  try {
    session = await getSignupSession(token);
  } catch {
    return (
      <main className="section">
        <div className="page-head">
          <span className="eyebrow">Signup Link</span>
          <h1>This signup link is not valid.</h1>
          <p>Ask Backfill to resend your setup text if you still need access.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Call Follow-Up</span>
        <h1>Review what Backfill captured from your call, then finish setup.</h1>
        <p>
          Start by correcting anything the agent got wrong. Then add the extra operating details we
          still need, like the location address and approximate headcount.
        </p>
      </div>

      <div className="three-up">
        <SectionCard title="1. Review call details">
          <p>Business name, location name, contact info, and the coverage problem are prefilled from the Retell call record.</p>
        </SectionCard>
        <SectionCard title="2. Fill the missing fields">
          <p>Add address, team size, and setup path so Backfill can route the next onboarding steps correctly.</p>
        </SectionCard>
        <SectionCard title="3. Save the record">
          <p>Submitting this creates or updates your business and location record in the Backfill operating ledger.</p>
        </SectionCard>
      </div>

      {status === "completed" ? (
        <section className="section">
          <div className="callout success-callout">
            <h3>Signup saved</h3>
            <p>
              Location <strong>{locationId}</strong> is now in Backfill. Continue in the{" "}
              <Link className="text-link" href={nextPath || "/dashboard"}>dashboard</Link>.
            </p>
          </div>
        </section>
      ) : null}

      {status === "error" ? (
        <section className="section">
          <div className="callout error-callout">
            <h3>Signup could not be completed</h3>
            <p>{message || "Check the form and try again."}</p>
          </div>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Confirm the record</h2>
            <p className="muted">Anything prefilled here came from the call transcript or after-call analysis.</p>
          </div>
        </div>
        <form className="setup-form" action={submitSignup.bind(null, token)}>
          <div className="form-grid">
            <label className="field">
              <span>Business name</span>
              <input name="business_name" defaultValue={session.business_name ?? ""} required />
            </label>
            <label className="field">
              <span>Location name</span>
              <input name="location_name" defaultValue={session.location_name ?? ""} required />
            </label>
            <label className="field">
              <span>Primary contact name</span>
              <input name="contact_name" defaultValue={session.contact_name ?? ""} />
            </label>
            <label className="field">
              <span>Primary contact phone</span>
              <input name="contact_phone" defaultValue={session.contact_phone ?? ""} required />
            </label>
            <label className="field">
              <span>Primary contact email</span>
              <input name="contact_email" defaultValue={session.contact_email ?? ""} />
            </label>
            <label className="field">
              <span>Your role</span>
              <input value={session.role_name ?? ""} disabled />
            </label>
            <label className="field">
              <span>Vertical</span>
              <select name="vertical" defaultValue={session.vertical ?? "other"}>
                <option value="restaurant">restaurant</option>
                <option value="healthcare">healthcare</option>
                <option value="warehouse">warehouse</option>
                <option value="retail">retail</option>
                <option value="hospitality">hospitality</option>
                <option value="other">other</option>
              </select>
            </label>
            <label className="field">
              <span>Locations in the business</span>
              <input
                name="location_count"
                type="number"
                min="1"
                defaultValue={session.location_count ?? undefined}
                placeholder="1"
              />
            </label>
            <label className="field">
              <span>Employees at this location</span>
              <input
                name="employee_count"
                type="number"
                min="1"
                defaultValue={session.employee_count ?? undefined}
                placeholder="25"
              />
            </label>
            <label className="field field-span-2">
              <span>Location address</span>
              <input
                name="address"
                defaultValue={session.address ?? ""}
                placeholder="123 Main St, Los Angeles, CA"
              />
            </label>
            <label className="field">
              <span>Preferred setup path</span>
              <select name="setup_kind" defaultValue={session.setup_kind ?? "manual_form"}>
                <option value="integration">integration</option>
                <option value="csv_upload">csv_upload</option>
                <option value="manual_form">manual_form</option>
              </select>
            </label>
            <label className="field">
              <span>Scheduling platform</span>
              <select name="scheduling_platform" defaultValue={session.scheduling_platform ?? "backfill_native"}>
                <option value="backfill_native">backfill_native</option>
                <option value="7shifts">7shifts</option>
                <option value="deputy">deputy</option>
                <option value="wheniwork">wheniwork</option>
                <option value="homebase">homebase</option>
              </select>
            </label>
            <label className="field">
              <span>Urgency</span>
              <input name="urgency" defaultValue={session.urgency ?? ""} placeholder="high, medium, low" />
            </label>
            <label className="field field-span-2">
              <span>Pain point summary</span>
              <textarea
                name="pain_point_summary"
                rows={3}
                defaultValue={session.pain_point_summary ?? ""}
                placeholder="What problem are you solving with Backfill?"
              />
            </label>
            <label className="field field-span-2">
              <span>Notes</span>
              <textarea
                name="notes"
                rows={4}
                defaultValue={session.notes ?? ""}
                placeholder="Anything the setup team should know."
              />
            </label>
          </div>
          <button className="button" type="submit">Save signup</button>
        </form>
      </section>
    </main>
  );
}
