"use client";

import { useAuth } from "@clerk/nextjs";
import { ArrowRight, LoaderCircle, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";

import type { DispositionCase, DispositionOverview } from "../../lib/api";
import styles from "./dispositions.module.css";

type EligibleTransaction = DispositionOverview["eligible_transactions"][number];

function cents(value: FormDataEntryValue | null) {
  return Math.round(Number(String(value ?? "").replace(/[$,]/g, "")) * 100);
}

function optionalCents(value: FormDataEntryValue | null) {
  const normalized = String(value ?? "").replace(/[$,]/g, "").trim();
  return normalized ? Math.round(Number(normalized) * 100) : null;
}

export function DispositionSetupWorkspace({
  canViewPrivateEconomics,
  dealIdByTransaction,
  eligibleTransactions,
  initialTransactionId,
}: {
  canViewPrivateEconomics: boolean;
  dealIdByTransaction: Record<string, string>;
  eligibleTransactions: EligibleTransaction[];
  initialTransactionId?: string;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const devEmail = useMemo(
    () => process.env.NEXT_PUBLIC_DEV_USER_EMAIL ?? "richardaustindugger@users.noreply.github.com",
    [],
  );
  const selectedTransactionId = eligibleTransactions.some(
    (item) => item.id === initialTransactionId,
  )
    ? initialTransactionId
    : eligibleTransactions[0]?.id;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const values = new FormData(event.currentTarget);
    const transactionId = String(values.get("transaction_id"));
    try {
      const token = await getToken().catch(() => null);
      const response = await fetch(`${apiBase}/api/v1/dispositions/cases`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : { "X-Dev-User-Email": devEmail }),
        },
        body: JSON.stringify({
          transaction_id: transactionId,
          strategy: values.get("strategy"),
          asking_price_cents: cents(values.get("asking_price")),
          minimum_acceptable_cents: cents(values.get("minimum_price")),
          desired_assignment_fee_cents: optionalCents(values.get("desired_assignment_fee")),
          operating_mode_key: "human_led",
          notes: values.get("notes") || null,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "Unable to open the disposition case.");
      }
      const dispositionCase = await response.json() as DispositionCase;
      const dealId = dealIdByTransaction[transactionId];
      router.push(
        dealId
          ? `/os/deals?view=all&display=queue&deal=${dealId}&tab=disposition`
          : `/os/dispositions?case=${dispositionCase.id}`,
      );
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to open the disposition case.");
      setBusy(false);
    }
  }

  if (!canViewPrivateEconomics) {
    return (
      <section className={styles.setupEmpty}>
        <strong>Private deal economics are restricted.</strong>
        <p>A disposition manager or owner must set the investor asking price, approved minimum, and assignment-fee target before buyer placement begins.</p>
        <Link href="/os/deals">
          Return to Deals <ArrowRight aria-hidden="true" size={15} />
        </Link>
      </section>
    );
  }

  if (!eligibleTransactions.length) {
    return (
      <section className={styles.setupEmpty}>
        <strong>No contracted deal is waiting for disposition setup.</strong>
        <p>When a purchase agreement is executed, open its Deal and start disposition from there.</p>
        <Link href="/os/deals?view=ready-for-disposition">
          Open Deals <ArrowRight aria-hidden="true" size={15} />
        </Link>
      </section>
    );
  }

  return (
    <section className={styles.setupLayout}>
      <form className={`${styles.openForm} ${styles.setupForm}`} onSubmit={submit}>
        <div className={styles.formTitle}><Plus aria-hidden="true" size={15} /><strong>Contracted property</strong></div>
        <label><span>Transaction</span><select defaultValue={selectedTransactionId} name="transaction_id" required>{eligibleTransactions.map((item) => <option key={item.id} value={item.id}>{item.asset_class === "land" ? "Land" : "House"} - {item.property_address} - {item.seller_name}</option>)}</select></label>
        <label><span>Disposition strategy</span><select name="strategy"><option value="assignment">Assignment</option><option value="double_close">Double close</option><option value="novation">Novation</option></select></label>
        <label><span>Investor asking price</span><input name="asking_price" inputMode="decimal" required /></label>
        <label><span>Approved minimum</span><input name="minimum_price" inputMode="decimal" required /></label>
        <label><span>Desired assignment fee (optional)</span><input name="desired_assignment_fee" inputMode="decimal" /><small>Internal target only. It is never included in an investor package.</small></label>
        <label><span>Internal notes</span><textarea name="notes" rows={3} /></label>
        <button disabled={busy} type="submit">{busy ? <LoaderCircle aria-hidden="true" className={styles.spin} size={15} /> : <Plus aria-hidden="true" size={15} />}Open disposition case</button>
        {message ? <p className={styles.notice} role="alert">{message}</p> : null}
      </form>
      <aside className={styles.setupContext}>
        <span>What happens next</span>
        <strong>One Deal remains the source of truth.</strong>
        <p>Stonegate freezes the approved floor and compensation plan, then opens the buyer package, matching, offers, and reconciliation tabs inside that Deal.</p>
        <Link href="/os/deals">Cancel and return to Deals</Link>
      </aside>
    </section>
  );
}
