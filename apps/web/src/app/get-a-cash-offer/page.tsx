import { CashOfferForm } from "./cash-offer-form";
import styles from "./page.module.css";

export const metadata = {
  title: "Get a Cash Offer | Georgia Wholesale OS",
  description: "Request a cash offer for a Georgia property.",
};

export default function GetCashOfferPage() {
  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>Georgia home buyers</p>
          <h1>Get a cash offer for your property</h1>
          <p>
            Share the basics and our acquisitions team will review the property,
            preserve your consent details, and create a lead in the operating system.
          </p>
        </div>
        <CashOfferForm />
      </section>
    </main>
  );
}
