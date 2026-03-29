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
  const contactPhone = String(formData.get("contact_phone") ?? "").trim();

  if (!businessName) {
    redirect(`/signup/${token}?status=error&message=Business+name+is+required`);
  }
  if (!contactPhone) {
    redirect(`/signup/${token}?status=error&message=Primary+contact+phone+is+required`);
  }

  try {
    const result = await completeSignupSession(token, {
      business_name: businessName,
      contact_name: String(formData.get("contact_name") ?? "").trim() || undefined,
      contact_phone: contactPhone,
      contact_email: String(formData.get("contact_email") ?? "").trim() || undefined,
      role_name: String(formData.get("role_name") ?? "").trim() || undefined,
      location_name: String(formData.get("location_name") ?? "").trim() || undefined,
      vertical: String(formData.get("vertical") ?? "").trim() || undefined,
      setup_kind: String(formData.get("setup_kind") ?? "").trim() || undefined,
      scheduling_platform: String(formData.get("scheduling_platform") ?? "").trim() || undefined,
      notes: String(formData.get("notes") ?? "").trim() || undefined,
      pain_point_summary: String(formData.get("pain_point_summary") ?? "").trim() || undefined,
      urgency: String(formData.get("urgency") ?? "").trim() || undefined,
      location_count: Number(formData.get("location_count") || 0) || undefined,
      employee_count: Number(formData.get("employee_count") || 0) || undefined,
      address: String(formData.get("address") ?? "").trim() || undefined,
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

  const isIntegrationPath = session.setup_kind === "integration";
  const nextStepLabel = isIntegrationPath
    ? `connect ${session.scheduling_platform ?? "your scheduler"}`
    : "start Backfill Shifts";

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Onboarding Handoff</span>
        <h1>Confirm what Backfill captured, then continue setup.</h1>
        <p>
          Most setup happens by phone or text. This page is just the confirmation step before you{" "}
          <strong>{nextStepLabel}</strong>.
        </p>
      </div>

      {status === "completed" ? (
        <section className="section">
          <div className="callout success-callout">
            <h3>Signup saved</h3>
            <p>
              Location <strong>{locationId}</strong> is now in Backfill. Continue to{" "}
              <Link className="text-link" href={nextPath || "/dashboard"}>
                {isIntegrationPath ? "scheduler setup" : "Backfill Shifts"}
              </Link>.
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
          <input type="hidden" name="location_name" value={session.location_name ?? ""} />
          <input type="hidden" name="vertical" value={session.vertical ?? ""} />
          <input type="hidden" name="setup_kind" value={session.setup_kind ?? ""} />
          <input type="hidden" name="scheduling_platform" value={session.scheduling_platform ?? ""} />
          <input type="hidden" name="pain_point_summary" value={session.pain_point_summary ?? ""} />
          <input type="hidden" name="urgency" value={session.urgency ?? ""} />
          <input type="hidden" name="notes" value={session.notes ?? ""} />
          <input type="hidden" name="address" value={session.address ?? ""} />
          <input type="hidden" name="employee_count" value={session.employee_count ?? ""} />
          <div className="form-grid">
            <label className="field">
              <span>Business name</span>
              <input name="business_name" defaultValue={session.business_name ?? ""} required />
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
              <input name="role_name" defaultValue={session.role_name ?? ""} />
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
          </div>
          <SectionCard title="What happens next">
            <p>
              After you confirm these details, Backfill will take you straight into{" "}
              {isIntegrationPath ? "scheduler connection" : "Backfill Shifts setup"} for your first
              location.
            </p>
          </SectionCard>
          <button className="button" type="submit">
            {isIntegrationPath ? "Confirm and connect scheduler" : "Confirm and start Backfill Shifts"}
          </button>
        </form>
      </section>
    </main>
  );
}
