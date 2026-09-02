"use client";

import { Check, FileUp, Search, UsersRound } from "lucide-react";
import { ChangeEvent, useMemo, useState } from "react";

import type { BuyerListItem, DispositionExecutionWorkspace } from "../../lib/api";
import styles from "./disposition-list-builder.module.css";

type Requester = <T>(path: string, options?: RequestInit) => Promise<T>;
type ImportedContact = {
  id: string;
  name: string;
  company: string;
  phone: string;
  email: string;
  error: string | null;
  existingBuyerId: string | null;
};

function normalizedPhone(value: string | null | undefined) {
  const digits = (value ?? "").replace(/\D/g, "");
  return digits.length > 10 ? digits.slice(-10) : digits;
}

function normalizedEmail(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase();
}

function normalizedCompany(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function splitDelimitedRow(row: string, delimiter: string) {
  const values: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < row.length; index += 1) {
    const character = row[index];
    if (character === '"') {
      if (quoted && row[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === delimiter && !quoted) {
      values.push(value.trim());
      value = "";
    } else {
      value += character;
    }
  }
  values.push(value.trim());
  return values;
}

function parseContacts(source: string, buyers: BuyerListItem[]) {
  const lines = source.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length < 2) return { contacts: [] as ImportedContact[], error: "Include a header row and at least one investor." };
  const delimiter = lines[0].includes("\t") ? "\t" : ",";
  const headers = splitDelimitedRow(lines[0], delimiter).map((value) => value.toLowerCase().replace(/[^a-z0-9]+/g, "_"));
  const column = (...names: string[]) => headers.findIndex((header) => names.includes(header));
  const nameIndex = column("name", "full_name", "contact", "contact_name", "buyer", "buyer_name");
  const companyIndex = column("company", "company_name", "business", "business_name");
  const phoneIndex = column("phone", "phone_number", "mobile", "cell", "cell_phone");
  const emailIndex = column("email", "email_address");
  if (nameIndex < 0 || (phoneIndex < 0 && emailIndex < 0)) {
    return { contacts: [] as ImportedContact[], error: "Use headers for Name and at least one of Phone or Email. Company is optional." };
  }
  const buyerByPhone = new Map(buyers.filter((buyer) => buyer.normalized_phone || buyer.phone).map((buyer) => [normalizedPhone(buyer.normalized_phone ?? buyer.phone), buyer.id]));
  const buyerByEmail = new Map(buyers.filter((buyer) => buyer.normalized_email || buyer.email).map((buyer) => [normalizedEmail(buyer.normalized_email ?? buyer.email), buyer.id]));
  const buyerByCompany = new Map(buyers.filter((buyer) => buyer.company_name).map((buyer) => [normalizedCompany(buyer.company_name), buyer.id]));
  const seen = new Set<string>();
  const seenCompanies = new Set<string>();
  const contacts = lines.slice(1).map((line, index): ImportedContact => {
    const values = splitDelimitedRow(line, delimiter);
    const name = values[nameIndex]?.trim() ?? "";
    const company = companyIndex >= 0 ? values[companyIndex]?.trim() ?? "" : "";
    const phone = phoneIndex >= 0 ? values[phoneIndex]?.trim() ?? "" : "";
    const email = emailIndex >= 0 ? values[emailIndex]?.trim() ?? "" : "";
    const phoneKey = normalizedPhone(phone);
    const emailKey = normalizedEmail(email);
    const companyKey = normalizedCompany(company);
    const identityKey = emailKey || phoneKey;
    const existingBuyerId = (emailKey ? buyerByEmail.get(emailKey) : null)
      ?? (phoneKey ? buyerByPhone.get(phoneKey) : null)
      ?? (companyKey ? buyerByCompany.get(companyKey) : null)
      ?? null;
    let error: string | null = null;
    if (!name) error = "Name is required";
    else if (!phone && !email) error = "Phone or email is required";
    else if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) error = "Email format is invalid";
    else if (phone && phoneKey.length !== 10) error = "Use a 10-digit US phone number";
    else if (identityKey && seen.has(identityKey)) error = "Duplicate row in this upload";
    else if (!existingBuyerId && companyKey && seenCompanies.has(companyKey)) error = "Company is repeated in this upload";
    if (identityKey) seen.add(identityKey);
    if (companyKey) seenCompanies.add(companyKey);
    return { id: `${index}-${identityKey || name}`, name, company, phone, email, error, existingBuyerId };
  });
  return { contacts, error: null as string | null };
}

export function DispositionListBuilder({
  buyers,
  caseId,
  currentBuyerIds,
  onComplete,
  request,
}: {
  buyers: BuyerListItem[];
  caseId: string;
  currentBuyerIds: string[];
  onComplete: (count: number) => Promise<void> | void;
  request: Requester;
}) {
  const [mode, setMode] = useState<"network" | "upload">(buyers.length ? "network" : "upload");
  const [search, setSearch] = useState("");
  const [selectedBuyerIds, setSelectedBuyerIds] = useState(() => new Set(currentBuyerIds));
  const [source, setSource] = useState("Name,Phone,Email,Company\n");
  const [contacts, setContacts] = useState<ImportedContact[]>([]);
  const [selectedContactIds, setSelectedContactIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const visibleBuyers = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return buyers;
    return buyers.filter((buyer) => [buyer.name, buyer.company_name, buyer.phone, buyer.email].some((value) => value?.toLowerCase().includes(query)));
  }, [buyers, search]);
  const selectedImportCount = contacts.filter((contact) => selectedContactIds.has(contact.id) && !contact.error).length;
  const totalSelected = new Set([...selectedBuyerIds, ...contacts.filter((contact) => selectedContactIds.has(contact.id)).map((contact) => contact.existingBuyerId).filter(Boolean) as string[]]).size
    + contacts.filter((contact) => selectedContactIds.has(contact.id) && !contact.error && !contact.existingBuyerId).length;

  function previewContacts(nextSource = source) {
    const parsed = parseContacts(nextSource, buyers);
    setContacts(parsed.contacts);
    setSelectedContactIds(new Set(parsed.contacts.filter((contact) => !contact.error).map((contact) => contact.id)));
    setError(parsed.error);
  }

  async function loadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setSource(text);
    previewContacts(text);
  }

  async function addToQuickDial() {
    if (!totalSelected || busy) return;
    setBusy(true);
    setError(null);
    try {
      const queueIds: string[] = [];
      const append = (buyerId: string) => {
        if (!queueIds.includes(buyerId)) queueIds.push(buyerId);
      };
      selectedBuyerIds.forEach(append);
      for (const contact of contacts) {
        if (!selectedContactIds.has(contact.id) || contact.error) continue;
        if (contact.existingBuyerId) {
          append(contact.existingBuyerId);
          continue;
        }
        const buyer = await request<BuyerListItem>("/api/v1/buyers", {
          method: "POST",
          body: JSON.stringify({
            name: contact.name,
            company_name: contact.company || null,
            phone: contact.phone || null,
            email: contact.email || null,
            buyer_type: "cash_buyer",
            status: "needs_review",
            source_key: "csv_import",
            source_detail: "Disposition QuickDial list import",
            relationship_status: "new",
            tier: "unclassified",
            temperature: "unknown",
            phone_contact_permission: false,
            sms_consent: false,
            permission_evidence_source: "buyer_list_import",
          }),
        });
        append(buyer.id);
      }
      if (!queueIds.length) throw new Error("Choose at least one valid investor.");
      const nextCurrentBuyerId = currentBuyerIds.find((buyerId) => queueIds.includes(buyerId)) ?? queueIds[0];
      await request<DispositionExecutionWorkspace>(`/api/v1/dispositions/cases/${caseId}/execution/session`, {
        method: "PATCH",
        body: JSON.stringify({
          queue_buyer_ids: queueIds,
          current_buyer_id: nextCurrentBuyerId,
          state: "active",
        }),
      });
      await onComplete(queueIds.length);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "The investor list could not be added to QuickDial.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.builder}>
      <nav aria-label="Investor list source">
        <button aria-pressed={mode === "network"} onClick={() => setMode("network")} type="button"><UsersRound size={16} />Buyer Network <span>{buyers.length}</span></button>
        <button aria-pressed={mode === "upload"} onClick={() => setMode("upload")} type="button"><FileUp size={16} />Upload or paste</button>
      </nav>

      {mode === "network" ? (
        <section className={styles.sourcePanel}>
          <label className={styles.search}><Search size={15} /><input onChange={(event) => setSearch(event.target.value)} placeholder="Search name, company, phone, or email" value={search} /></label>
          {visibleBuyers.length ? <div className={styles.buyerList}>{visibleBuyers.map((buyer) => {
            const selected = selectedBuyerIds.has(buyer.id);
            return <label data-selected={selected} key={buyer.id}><input checked={selected} onChange={() => setSelectedBuyerIds((current) => { const next = new Set(current); if (next.has(buyer.id)) next.delete(buyer.id); else next.add(buyer.id); return next; })} type="checkbox" /><span><strong>{buyer.name}</strong><small>{buyer.company_name ?? "Independent investor"} · {buyer.phone ?? buyer.email ?? "No contact recorded"}</small></span>{selected ? <Check size={16} /> : null}</label>;
          })}</div> : <p className={styles.empty}>No Buyer Network contacts match this search. Use Upload or paste to add new investors.</p>}
        </section>
      ) : (
        <section className={styles.sourcePanel}>
          <div className={styles.uploadRow}><label><FileUp size={16} /><span>Choose CSV file</span><input accept=".csv,text/csv,text/tab-separated-values" onChange={(event) => void loadFile(event)} type="file" /></label><small>Headers: Name plus Phone or Email. Company is optional.</small></div>
          <label className={styles.paste}><span>Or paste rows from a spreadsheet</span><textarea onChange={(event) => setSource(event.target.value)} rows={7} value={source} /></label>
          <button className={styles.previewButton} onClick={() => previewContacts()} type="button">Preview contacts</button>
          {contacts.length ? <div className={styles.contactPreview}><header><strong>{contacts.length} rows found</strong><span>{selectedImportCount} selected</span></header>{contacts.map((contact) => {
            const selected = selectedContactIds.has(contact.id);
            return <label data-error={Boolean(contact.error)} data-selected={selected} key={contact.id}><input checked={selected} disabled={Boolean(contact.error)} onChange={() => setSelectedContactIds((current) => { const next = new Set(current); if (next.has(contact.id)) next.delete(contact.id); else next.add(contact.id); return next; })} type="checkbox" /><span><strong>{contact.name || "Missing name"}</strong><small>{contact.phone || contact.email || "Missing contact information"}</small></span><b>{contact.error ?? (contact.existingBuyerId ? "Existing" : "New")}</b></label>;
          })}</div> : null}
        </section>
      )}

      {error ? <p className={styles.error} role="alert">{error}</p> : null}
      <footer><span><strong>{totalSelected}</strong> investor{totalSelected === 1 ? "" : "s"} selected</span><button disabled={!totalSelected || busy} onClick={() => void addToQuickDial()} type="button">{busy ? "Building QuickDial…" : `Save ${totalSelected} to QuickDial`}</button></footer>
    </div>
  );
}
