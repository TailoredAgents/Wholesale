"use client";

import { useAuth } from "@clerk/nextjs";
import {
  BadgeCheck,
  Building2,
  Download,
  FileLock2,
  FileUp,
  Plus,
  ReceiptText,
  Trash2,
  UserRoundCheck,
  WalletCards,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type {
  AccountingSetup,
  VendorAccounting,
} from "../../lib/api";
import {
  Button,
  Checkbox,
  IconButton,
  StatusBadge,
} from "../_components/design-system";
import { labelize } from "../os-utils";
import styles from "./vendor-accounting.module.css";

type BillLineDraft = {
  key: number;
  description: string;
  amount: string;
  account: string;
};

function money(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function cents(value: string) {
  const parsed = Number(value.replace(/[$,]/g, ""));
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function date(value: string | null) {
  if (!value) return "No due date";
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(
    new Date(value),
  );
}

function fileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function tone(
  status: string,
): "neutral" | "info" | "success" | "warning" | "danger" {
  if (["active", "approved", "paid", "verified", "clean"].includes(status)) {
    return "success";
  }
  if (["received", "payable", "requested"].includes(status)) return "warning";
  if (["draft", "not_requested"].includes(status)) return "info";
  if (["disputed", "infected", "overdue"].includes(status)) return "danger";
  return "neutral";
}

export function VendorAccountingPanel({
  setup,
  workspace,
  permissions,
}: {
  setup: AccountingSetup;
  workspace: VendorAccounting;
  permissions: {
    manageVendors: boolean;
    manageEvidence: boolean;
    approveBills: boolean;
  };
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedVendorId, setSelectedVendorId] = useState(
    workspace.vendors[0]?.id ?? "",
  );
  const [selectedBillId, setSelectedBillId] = useState("");
  const [billLines, setBillLines] = useState<BillLineDraft[]>([
    { key: 1, description: "", amount: "", account: "" },
  ]);
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devUserEmail = useMemo(
    () =>
      process.env.NEXT_PUBLIC_DEV_USER_EMAIL ??
      "richardaustindugger@users.noreply.github.com",
    [],
  );
  const expenseAccounts = setup.accounts.filter(
    (account) =>
      account.is_active &&
      ["expense", "cost_of_revenue"].includes(account.account_type),
  );

  async function headers(contentType = "application/json") {
    const token = await getToken().catch(() => null);
    const result: Record<string, string> = { "Content-Type": contentType };
    if (token) result.Authorization = `Bearer ${token}`;
    else result["X-Dev-User-Email"] = devUserEmail;
    return result;
  }

  async function jsonRequest(
    path: string,
    body: Record<string, unknown>,
    method = "POST",
  ) {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers: await headers(),
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const data = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      throw new Error(data?.detail ?? "Finance request failed.");
    }
    return response;
  }

  async function action(work: () => Promise<void>, success: string) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      setMessage(success);
      router.refresh();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Finance request failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function createVendor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    await action(async () => {
      await jsonRequest("/api/v1/finance/vendors", {
        name: String(form.get("name") ?? ""),
        company_name: String(form.get("company_name") ?? "") || null,
        email: String(form.get("email") ?? "") || null,
        phone: String(form.get("phone") ?? "") || null,
        vendor_type: String(form.get("vendor_type") ?? "vendor"),
        default_expense_account_key:
          String(form.get("default_expense_account_key") ?? "") || null,
        payment_terms_days: Number(form.get("payment_terms_days") ?? 0),
        tax_reportable: form.get("tax_reportable") === "on",
        w9_status:
          form.get("tax_reportable") === "on" ? "requested" : "not_required",
        remittance_address:
          String(form.get("remittance_address") ?? "") || null,
        notes: String(form.get("notes") ?? "") || null,
      });
      formElement.reset();
    }, "Vendor added. W-9 and bill tracking are ready.");
  }

  async function createBill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const lines = billLines
      .map((line) => ({
        description: line.description.trim(),
        amount_cents: cents(line.amount),
        expense_account_key: line.account,
      }))
      .filter(
        (line) =>
          line.description && line.amount_cents > 0 && line.expense_account_key,
      );
    await action(async () => {
      if (!lines.length) throw new Error("Add at least one complete bill line.");
      await jsonRequest("/api/v1/finance/vendor-bills", {
        vendor_profile_id: String(form.get("vendor_profile_id") ?? ""),
        bill_number: String(form.get("bill_number") ?? "") || null,
        issue_at: String(form.get("issue_at") ?? "") || null,
        due_at: String(form.get("due_at") ?? "") || null,
        description: String(form.get("description") ?? ""),
        notes: String(form.get("notes") ?? "") || null,
        lines,
      });
      formElement.reset();
      setBillLines([{ key: Date.now(), description: "", amount: "", account: "" }]);
    }, "Draft bill added. Attach the invoice before approval.");
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = form.get("file");
    if (!(file instanceof File) || !file.size) {
      setMessage("Choose a document to upload.");
      return;
    }
    await action(async () => {
      const query = new URLSearchParams({
        file_name: file.name,
        document_type: String(form.get("document_type") ?? "other"),
        title: String(form.get("title") ?? file.name),
      });
      const vendorId = String(form.get("vendor_profile_id") ?? "");
      const billId = String(form.get("vendor_bill_id") ?? "");
      const notes = String(form.get("notes") ?? "");
      if (vendorId) query.set("vendor_profile_id", vendorId);
      if (billId) query.set("vendor_bill_id", billId);
      if (notes) query.set("notes", notes);
      const response = await fetch(
        `${apiBaseUrl}/api/v1/finance/documents?${query}`,
        {
          method: "POST",
          headers: await headers(file.type || "application/octet-stream"),
          body: file,
        },
      );
      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as {
          detail?: string;
        } | null;
        throw new Error(data?.detail ?? "Document upload failed.");
      }
      formElement.reset();
    }, "Private evidence uploaded and linked.");
  }

  async function downloadDocument(documentId: string, fileName: string) {
    await action(async () => {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/finance/documents/${documentId}/content`,
        { headers: await headers("application/octet-stream") },
      );
      if (!response.ok) throw new Error("Document download failed.");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = fileName;
      anchor.click();
      URL.revokeObjectURL(url);
    }, "Private document downloaded. Access was logged.");
  }

  function updateLine(
    key: number,
    field: keyof Omit<BillLineDraft, "key">,
    value: string,
  ) {
    setBillLines((current) =>
      current.map((line) =>
        line.key === key ? { ...line, [field]: value } : line,
      ),
    );
  }

  return (
    <section className={styles.workspace}>
      <header className={styles.header}>
        <div>
          <span>F6D vendor accounting</span>
          <h2>Vendors, bills, and private evidence</h2>
        </div>
        <StatusBadge
          tone={workspace.summary.overdue_bills ? "danger" : "success"}
        >
          {workspace.summary.overdue_bills
            ? `${workspace.summary.overdue_bills} overdue`
            : "Payables current"}
        </StatusBadge>
      </header>

      <div className={styles.metrics}>
        <div>
          <Building2 size={17} />
          <span>Active vendors</span>
          <strong>{workspace.summary.active_vendors}</strong>
          <small>{workspace.summary.contractors} contractors</small>
        </div>
        <div>
          <UserRoundCheck size={17} />
          <span>W-9 action</span>
          <strong>{workspace.summary.w9_action_required}</strong>
          <small>Tax-reportable vendors</small>
        </div>
        <div>
          <ReceiptText size={17} />
          <span>Open payable</span>
          <strong>{money(workspace.summary.open_payable_cents)}</strong>
          <small>{workspace.summary.open_payables} approved bills</small>
        </div>
        <div>
          <WalletCards size={17} />
          <span>Paid year to date</span>
          <strong>{money(workspace.summary.paid_year_to_date_cents)}</strong>
          <small>{workspace.summary.draft_bills} draft bills</small>
        </div>
        <div>
          <FileLock2 size={17} />
          <span>Private evidence</span>
          <strong>{workspace.summary.private_documents}</strong>
          <small>Access audited</small>
        </div>
      </div>

      <section className={styles.directory}>
        <div className={styles.sectionHeading}>
          <div>
            <span>Vendor directory</span>
            <h3>Contractors and service providers</h3>
          </div>
          <strong>{workspace.vendors.length} records</strong>
        </div>
        {workspace.vendors.length ? (
          <div className={styles.vendorGrid}>
            {workspace.vendors.map((vendor) => (
              <article key={vendor.id}>
                <div className={styles.vendorTitle}>
                  <div>
                    <strong>{vendor.name}</strong>
                    <span>{labelize(vendor.vendor_type)}</span>
                  </div>
                  <StatusBadge tone={tone(vendor.w9_status)}>
                    W-9 {labelize(vendor.w9_status)}
                  </StatusBadge>
                </div>
                <dl>
                  <div>
                    <dt>Open bills</dt>
                    <dd>{vendor.open_bill_count}</dd>
                  </div>
                  <div>
                    <dt>Paid YTD</dt>
                    <dd>{money(vendor.paid_year_to_date_cents)}</dd>
                  </div>
                  <div>
                    <dt>Terms</dt>
                    <dd>{vendor.payment_terms_days || "Due now"}{vendor.payment_terms_days ? " days" : ""}</dd>
                  </div>
                </dl>
                <small>{vendor.email ?? vendor.phone ?? "No contact method recorded"}</small>
                {permissions.manageEvidence &&
                vendor.tax_reportable &&
                vendor.w9_status === "received" ? (
                  <Button
                    disabled={busy}
                    icon={<BadgeCheck size={14} />}
                    onClick={() =>
                      void action(
                        async () => {
                          await jsonRequest(
                            `/api/v1/finance/vendors/${vendor.id}/w9-status`,
                            { status: "verified", notes: null },
                          );
                        },
                        `${vendor.name} W-9 verified.`,
                      )
                    }
                    size="small"
                    type="button"
                    variant="secondary"
                  >
                    Verify W-9
                  </Button>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.empty}>
            Add the first contractor or service provider to start bill tracking.
          </p>
        )}
      </section>

      <section>
        <div className={styles.sectionHeading}>
          <div>
            <span>Accounts payable</span>
            <h3>Bill register</h3>
          </div>
          <strong>{workspace.bills.length} bills</strong>
        </div>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Vendor / bill</th>
                <th>Status</th>
                <th>Due</th>
                <th>Itemization</th>
                <th>Evidence</th>
                <th>Amount</th>
                <th>Control</th>
              </tr>
            </thead>
            <tbody>
              {workspace.bills.length ? (
                workspace.bills.map((bill) => (
                  <tr key={bill.id}>
                    <td>
                      <strong>{bill.vendor_name}</strong>
                      <small>{bill.bill_number} · {bill.description}</small>
                    </td>
                    <td>
                      <StatusBadge tone={tone(bill.status)}>
                        {labelize(bill.status)}
                      </StatusBadge>
                    </td>
                    <td>{date(bill.due_at)}</td>
                    <td>
                      {bill.lines.map((line) => (
                        <span key={line.id}>
                          {labelize(line.expense_account_key)} {money(line.amount_cents)}
                        </span>
                      ))}
                    </td>
                    <td>{bill.evidence_count} files</td>
                    <td><strong>{money(bill.amount_cents)}</strong></td>
                    <td>
                      {bill.status === "draft" && permissions.approveBills ? (
                        <Button
                          disabled={busy}
                          icon={<BadgeCheck size={14} />}
                          onClick={() =>
                            void action(
                              async () => {
                                await jsonRequest(
                                  `/api/v1/finance/vendor-bills/${bill.id}/approve`,
                                  {},
                                );
                              },
                              `${bill.bill_number} approved and added to posting control.`,
                            )
                          }
                          size="small"
                          type="button"
                        >
                          Approve
                        </Button>
                      ) : bill.financial_obligation_id ? (
                        <span className={styles.linked}>Posting linked</span>
                      ) : (
                        <span>Draft</span>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7}>No vendor bills have been recorded.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {(permissions.manageVendors || permissions.manageEvidence) ? (
        <div className={styles.composers}>
          {permissions.manageVendors ? (
            <details>
              <summary><Plus size={15} /> Add vendor</summary>
              <form onSubmit={createVendor}>
                <label>Name<input name="name" required /></label>
                <label>Company<input name="company_name" /></label>
                <label>Type<select name="vendor_type" defaultValue="contractor"><option value="contractor">Contractor</option><option value="vendor">Vendor</option><option value="closing_service">Closing service</option><option value="funding_partner">Funding partner</option><option value="other">Other</option></select></label>
                <label>Email<input name="email" type="email" /></label>
                <label>Phone<input name="phone" type="tel" /></label>
                <label>Default account<select name="default_expense_account_key" defaultValue=""><option value="">Select later</option>{expenseAccounts.map((account) => <option key={account.id} value={account.system_key}>{account.code} · {account.name}</option>)}</select></label>
                <label>Payment terms<input min="0" name="payment_terms_days" type="number" defaultValue="0" /></label>
                <label className={styles.wide}>Remittance address<textarea name="remittance_address" rows={2} /></label>
                <Checkbox className={styles.wide} description="Tracks receipt and review; tax IDs stay only inside the private document." label="Tax-reportable contractor or vendor" name="tax_reportable" />
                <label className={styles.wide}>Internal notes<textarea name="notes" rows={2} /></label>
                <Button disabled={busy} icon={<Plus size={14} />} type="submit">Add vendor</Button>
              </form>
            </details>
          ) : null}

          {permissions.manageVendors && workspace.vendors.length ? (
            <details>
              <summary><ReceiptText size={15} /> Enter bill</summary>
              <form onSubmit={createBill}>
                <label>Vendor<select name="vendor_profile_id" required value={selectedVendorId} onChange={(event) => setSelectedVendorId(event.target.value)}>{workspace.vendors.filter((vendor) => vendor.status === "active").map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>
                <label>Bill number<input name="bill_number" /></label>
                <label>Issue date<input name="issue_at" type="date" /></label>
                <label>Due date<input name="due_at" type="date" /></label>
                <label className={styles.wide}>Description<input name="description" required /></label>
                <div className={styles.billLines}>
                  <div><strong>Bill lines</strong><Button icon={<Plus size={13} />} onClick={() => setBillLines((current) => [...current, { key: Date.now(), description: "", amount: "", account: "" }])} size="small" type="button" variant="quiet">Add line</Button></div>
                  {billLines.map((line, index) => (
                    <div className={styles.billLine} key={line.key}>
                      <label>Description<input aria-label={`Line ${index + 1} description`} value={line.description} onChange={(event) => updateLine(line.key, "description", event.target.value)} /></label>
                      <label>Amount<input aria-label={`Line ${index + 1} amount`} inputMode="decimal" placeholder="0.00" value={line.amount} onChange={(event) => updateLine(line.key, "amount", event.target.value)} /></label>
                      <label>Account<select aria-label={`Line ${index + 1} account`} value={line.account} onChange={(event) => updateLine(line.key, "account", event.target.value)}><option value="">Choose account</option>{expenseAccounts.map((account) => <option key={account.id} value={account.system_key}>{account.code} · {account.name}</option>)}</select></label>
                      <IconButton disabled={billLines.length === 1} label="Remove line" onClick={() => setBillLines((current) => current.filter((item) => item.key !== line.key))}><Trash2 size={14} /></IconButton>
                    </div>
                  ))}
                </div>
                <label className={styles.wide}>Internal notes<textarea name="notes" rows={2} /></label>
                <Button disabled={busy} icon={<ReceiptText size={14} />} type="submit">Save draft bill</Button>
              </form>
            </details>
          ) : null}

          {permissions.manageEvidence && workspace.vendors.length ? (
            <details>
              <summary><FileUp size={15} /> Upload private evidence</summary>
              <form onSubmit={uploadDocument}>
                <label>Vendor<select name="vendor_profile_id" required value={selectedVendorId} onChange={(event) => setSelectedVendorId(event.target.value)}>{workspace.vendors.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>
                <label>Related bill<select name="vendor_bill_id" value={selectedBillId} onChange={(event) => setSelectedBillId(event.target.value)}><option value="">Vendor record only</option>{workspace.bills.filter((bill) => bill.vendor_profile_id === selectedVendorId).map((bill) => <option key={bill.id} value={bill.id}>{bill.bill_number} · {money(bill.amount_cents)}</option>)}</select></label>
                <label>Document type<select name="document_type" defaultValue="invoice"><option value="invoice">Invoice</option><option value="receipt">Receipt</option><option value="w9">W-9</option><option value="payment_evidence">Payment evidence</option><option value="closing_statement">Closing statement</option><option value="contract">Contract</option><option value="other">Other</option></select></label>
                <label>Title<input name="title" required /></label>
                <label className={styles.wide}>File<input accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx,.csv" name="file" required type="file" /></label>
                <label className={styles.wide}>Notes<textarea name="notes" rows={2} /></label>
                <Button disabled={busy} icon={<FileUp size={14} />} type="submit">Upload evidence</Button>
              </form>
            </details>
          ) : null}
        </div>
      ) : null}

      {permissions.manageEvidence && workspace.documents.length ? (
        <section>
          <div className={styles.sectionHeading}>
            <div>
              <span>Private document register</span>
              <h3>Evidence and tax files</h3>
            </div>
            <strong>{workspace.documents.length} active</strong>
          </div>
          <div className={styles.documents}>
            {workspace.documents.map((documentItem) => (
              <div key={documentItem.id}>
                <FileLock2 size={16} />
                <div>
                  <strong>{documentItem.title}</strong>
                  <span>{labelize(documentItem.document_type)} · {fileSize(documentItem.file_size)} · {date(documentItem.occurred_at)}</span>
                </div>
                <StatusBadge tone={tone(documentItem.malware_scan_status)}>
                  {documentItem.is_sensitive ? "Sensitive" : labelize(documentItem.status)}
                </StatusBadge>
                <IconButton
                  disabled={busy}
                  label={`Download ${documentItem.title}`}
                  onClick={() => void downloadDocument(documentItem.id, documentItem.file_name)}
                >
                  <Download size={15} />
                </IconButton>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <p className={styles.message} aria-live="polite">{message}</p>
    </section>
  );
}
