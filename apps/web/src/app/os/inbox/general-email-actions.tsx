"use client";

import { Archive, Link2, RotateCcw, UserPlus } from "lucide-react";
import { FormEvent, useState } from "react";

import {
  Button,
  Dialog,
  FormField,
  Select,
  TextArea,
  TextInput,
} from "../_components/design-system";
import styles from "./inbox.module.css";

export type LinkableLead = {
  id: string;
  seller_name: string;
  property_address: string;
};

type MailCategory = "general" | "vendor" | "administrative" | "spam" | "archived";

export function GeneralEmailActions({
  canManage,
  canClassify,
  category,
  closed,
  leads,
  leadsLoading,
  mergedConversationId,
  onClassify,
  onConvert,
  onLink,
  onOpenMerged,
}: {
  canManage: boolean;
  canClassify: boolean;
  category: string | null;
  closed: boolean;
  leads: LinkableLead[];
  leadsLoading: boolean;
  mergedConversationId: string | null;
  onClassify: (category: MailCategory, close: boolean, reason?: string) => Promise<void>;
  onConvert: (payload: {
    asset_class: "house" | "land";
    street_address: string;
    city: string;
    state: string;
    postal_code: string;
    county: string | null;
    property_type: string | null;
    parcel_id: string | null;
  }) => Promise<void>;
  onLink: (leadId: string) => Promise<void>;
  onOpenMerged: (conversationId: string) => Promise<void>;
}) {
  const [dialog, setDialog] = useState<"convert" | "link" | "classify" | null>(null);
  const [status, setStatus] = useState<"idle" | "working">("idle");
  const [streetAddress, setStreetAddress] = useState("");
  const [assetClass, setAssetClass] = useState<"house" | "land">("house");
  const [city, setCity] = useState("");
  const [state, setState] = useState("GA");
  const [postalCode, setPostalCode] = useState("");
  const [county, setCounty] = useState("");
  const [propertyType, setPropertyType] = useState("");
  const [parcelId, setParcelId] = useState("");
  const [leadId, setLeadId] = useState("");
  const [mailCategory, setMailCategory] = useState<MailCategory>("vendor");
  const [classificationReason, setClassificationReason] = useState("");

  async function run(action: () => Promise<void>) {
    setStatus("working");
    try {
      await action();
      setDialog(null);
    } finally {
      setStatus("idle");
    }
  }

  async function submitConversion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(() =>
      onConvert({
        asset_class: assetClass,
        street_address: streetAddress.trim(),
        city: city.trim(),
        state: state.trim().toUpperCase(),
        postal_code: postalCode.trim(),
        county: county.trim() || null,
        property_type: propertyType || (assetClass === "land" ? "land" : null),
        parcel_id: parcelId.trim() || null,
      }),
    );
  }

  async function submitLink(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!leadId) return;
    await run(() => onLink(leadId));
  }

  async function submitClassification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(() => onClassify(mailCategory, true, classificationReason.trim() || undefined));
  }

  if (!canManage && !canClassify) {
    return <p className={styles.mutedText}>Ask a lead manager to handle this email.</p>;
  }

  if (closed) {
    const wasMerged = category === "linked_to_lead" && Boolean(mergedConversationId);
    return (
      <div className={styles.generalEmailResolution}>
        <p>
          {wasMerged ? "This email history was merged into an existing seller lead." : (
            <>This message is archived as <strong>{category?.replaceAll("_", " ") || "general mail"}</strong>.</>
          )}
        </p>
        {wasMerged && mergedConversationId ? (
          <Button
            icon={<Link2 aria-hidden="true" size={14} />}
            onClick={() => run(() => onOpenMerged(mergedConversationId))}
            size="small"
            type="button"
            variant="secondary"
          >
            Open linked seller thread
          </Button>
        ) : canClassify ? (
          <Button
            icon={<RotateCcw aria-hidden="true" size={14} />}
            loading={status === "working"}
            onClick={() => run(() => onClassify((category as MailCategory) || "general", false))}
            size="small"
            type="button"
            variant="secondary"
          >
            Restore to inbox
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <div className={styles.generalEmailActions}>
        {canManage ? (
          <>
            <Button
              icon={<UserPlus aria-hidden="true" size={14} />}
              onClick={() => setDialog("convert")}
              size="small"
              type="button"
            >
              Convert to lead
            </Button>
            <Button
              icon={<Link2 aria-hidden="true" size={14} />}
              onClick={() => setDialog("link")}
              size="small"
              type="button"
              variant="secondary"
            >
              Link to existing lead
            </Button>
          </>
        ) : null}
        {canClassify ? (
          <Button
            icon={<Archive aria-hidden="true" size={14} />}
            onClick={() => setDialog("classify")}
            size="small"
            type="button"
            variant="quiet"
          >
            Mark non-lead and archive
          </Button>
        ) : null}
      </div>

      <Dialog
        description="The sender becomes a seller lead, this entire email thread stays attached, and property research starts automatically."
        footer={
          <>
            <Button onClick={() => setDialog(null)} type="button" variant="quiet">Cancel</Button>
            <Button disabled={status === "working"} form="convert-email-to-lead" loading={status === "working"} type="submit">
              Create seller lead
            </Button>
          </>
        }
        onClose={() => setDialog(null)}
        open={dialog === "convert"}
        title="Convert email to lead"
      >
        <form className={styles.generalEmailForm} id="convert-email-to-lead" onSubmit={submitConversion}>
          <FormField htmlFor="email-lead-asset" label="Lead type">
            <Select id="email-lead-asset" onChange={(event) => setAssetClass(event.target.value as "house" | "land")} value={assetClass}>
              <option value="house">House</option>
              <option value="land">Land</option>
            </Select>
          </FormField>
          <FormField htmlFor="email-lead-street" label="Street address">
            <TextInput id="email-lead-street" onChange={(event) => setStreetAddress(event.target.value)} required value={streetAddress} />
          </FormField>
          <div className={styles.generalEmailFormGrid}>
            <FormField htmlFor="email-lead-city" label="City">
              <TextInput id="email-lead-city" onChange={(event) => setCity(event.target.value)} required value={city} />
            </FormField>
            <FormField htmlFor="email-lead-state" label="State">
              <TextInput id="email-lead-state" maxLength={2} minLength={2} onChange={(event) => setState(event.target.value)} required value={state} />
            </FormField>
            <FormField htmlFor="email-lead-zip" label="ZIP code">
              <TextInput id="email-lead-zip" onChange={(event) => setPostalCode(event.target.value)} required value={postalCode} />
            </FormField>
          </div>
          <div className={styles.generalEmailFormGrid}>
            <FormField htmlFor="email-lead-county" label="County" optional>
              <TextInput id="email-lead-county" onChange={(event) => setCounty(event.target.value)} value={county} />
            </FormField>
            <FormField htmlFor="email-lead-property-type" label="Property type" optional>
              <Select id="email-lead-property-type" onChange={(event) => setPropertyType(event.target.value)} value={propertyType}>
                <option value="">Not captured</option>
                <option value="single_family">Single family</option>
                <option value="multi_family">Multi-family</option>
                <option value="condo">Condo</option>
                <option value="townhouse">Townhouse</option>
                <option value="mobile_home">Mobile home</option>
                <option value="land">Land</option>
              </Select>
            </FormField>
            <FormField htmlFor="email-lead-parcel" label="Parcel / APN" optional>
              <TextInput id="email-lead-parcel" maxLength={255} onChange={(event) => setParcelId(event.target.value)} value={parcelId} />
            </FormField>
          </div>
        </form>
      </Dialog>

      <Dialog
        description="The email history and sender address will be merged into the selected seller’s existing conversation."
        footer={
          <>
            <Button onClick={() => setDialog(null)} type="button" variant="quiet">Cancel</Button>
            <Button disabled={!leadId || status === "working"} form="link-email-to-lead" loading={status === "working"} type="submit">
              Link email history
            </Button>
          </>
        }
        onClose={() => setDialog(null)}
        open={dialog === "link"}
        title="Link to an existing lead"
      >
        <form className={styles.generalEmailForm} id="link-email-to-lead" onSubmit={submitLink}>
          <FormField htmlFor="email-existing-lead" label="Seller lead">
            <Select disabled={leadsLoading} id="email-existing-lead" onChange={(event) => setLeadId(event.target.value)} required value={leadId}>
              <option value="">{leadsLoading ? "Loading leads..." : "Select a lead"}</option>
              {leads.map((lead) => (
                <option key={lead.id} value={lead.id}>{lead.seller_name} — {lead.property_address}</option>
              ))}
            </Select>
          </FormField>
          {!leadsLoading && leads.length === 0 ? <p className={styles.mutedText}>No active seller leads are available.</p> : null}
        </form>
      </Dialog>

      <Dialog
        description="This keeps the correspondence for your records but removes it from active Inbox views."
        footer={
          <>
            <Button onClick={() => setDialog(null)} type="button" variant="quiet">Cancel</Button>
            <Button form="classify-general-email" loading={status === "working"} type="submit">Archive email</Button>
          </>
        }
        onClose={() => setDialog(null)}
        open={dialog === "classify"}
        title="Mark as non-lead mail"
      >
        <form className={styles.generalEmailForm} id="classify-general-email" onSubmit={submitClassification}>
          <FormField htmlFor="general-email-category" label="Category">
            <Select id="general-email-category" onChange={(event) => setMailCategory(event.target.value as MailCategory)} value={mailCategory}>
              <option value="vendor">Vendor</option>
              <option value="administrative">Administrative</option>
              <option value="spam">Spam</option>
              <option value="archived">Other handled mail</option>
            </Select>
          </FormField>
          <FormField htmlFor="general-email-reason" label="Note" optional>
            <TextArea id="general-email-reason" maxLength={500} onChange={(event) => setClassificationReason(event.target.value)} placeholder="Why this is not a seller lead" rows={3} value={classificationReason} />
          </FormField>
        </form>
      </Dialog>
    </>
  );
}
