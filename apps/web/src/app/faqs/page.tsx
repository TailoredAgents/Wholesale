import type { Metadata } from "next";
import { ArrowRight, Phone } from "lucide-react";
import Link from "next/link";

import { PublicSiteFooter } from "../public-site-footer";
import { PublicSiteHeader } from "../public-site-header";
import { directOfferDisclosure, siteConfig } from "../site-config";
import styles from "../public-content.module.css";

export const metadata: Metadata = {
  title: "Cash Home Offer FAQs | Stonegate Home Buyers",
  description: "Straight answers about Stonegate cash offers, as-is sales, repairs, fees, timing, contracts, and seller privacy.",
  alternates: { canonical: "/faqs" },
};

const faqs = [
  { question: "Is requesting an offer free and without obligation?", answer: "Yes. Stonegate does not charge for the property review, and submitting information does not require you to accept an offer or sign a purchase agreement." },
  { question: "How does Stonegate determine an offer?", answer: "We consider property characteristics, current condition, nearby market information, expected repairs, holding and resale costs, local demand, title or access concerns, and transaction risk. An offer is an investment decision, not an appraisal." },
  { question: "Will a direct cash offer be below retail market value?", answer: "Usually, yes. A prepared retail listing may produce a higher price. A direct offer accounts for repairs, resale costs, time, and risk in exchange for an as-is process with fewer listing steps." },
  { question: "Do I need to repair or clean the house first?", answer: "No. You can request a review in the property's current condition. Sharing known repair issues helps us understand the property, but you do not need to hire contractors or remove every item before starting." },
  { question: "Does Stonegate charge an agent commission?", answer: "Stonegate does not charge the seller an agent commission for a direct purchase. The written agreement should identify any transaction-specific costs so you can review the expected net amount." },
  { question: "How fast can a sale close?", answer: "There is no universal guaranteed closing date. Timing depends on the mutually accepted contract, title review, ownership, access, and property verification. Tell us your preferred timeline so it can be considered before an agreement is signed." },
  { question: "Can you review inherited, tenant-occupied, or damaged property?", answer: "Yes, those are situations Stonegate can discuss. Probate or title status, tenant rights, insurance issues, and property access may affect what is possible and should be reviewed early." },
  { question: "Will Stonegate inspect the property?", answer: "Property access or verification may be needed before closing. The exact review and any related contract rights should be stated in the written purchase agreement." },
  { question: "Could the purchase contract be assigned to another investor?", answer: "Possibly. Stonegate may purchase directly or assign contractual purchase rights when the written agreement permits it. The contract controls the parties' rights, and sellers may seek independent legal advice before signing." },
  { question: "How will Stonegate contact me?", answer: "We use the phone or email information you provide for the property inquiry. Text messaging is optional and requires separate consent. You can reply STOP to opt out of texts or call Stonegate for help." },
];

export default function FaqsPage() {
  return (
    <main className={styles.page}>
      <PublicSiteHeader />
      <section className={styles.hero}>
        <p className={styles.eyebrow}>Frequently asked questions</p>
        <h1>Straight answers before you request or accept an offer.</h1>
        <p>Understand the process, tradeoffs, costs, timing, and contract questions that matter most.</p>
        <div className={styles.heroActions}>
          <Link className={styles.primaryAction} href="/get-a-cash-offer">Start My Offer <ArrowRight size={17} aria-hidden="true" /></Link>
          <a className={styles.secondaryAction} href={siteConfig.phoneHref}><Phone size={17} aria-hidden="true" /> {siteConfig.phoneDisplay}</a>
        </div>
      </section>

      <section className={styles.faqSection}>
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>Before you decide</p>
          <h2>What Georgia property owners commonly ask</h2>
        </div>
        <div className={styles.faqList}>
          {faqs.map((faq) => (
            <details key={faq.question}>
              <summary>{faq.question}</summary>
              <p>{faq.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className={styles.finalCta}>
        <div><p className={styles.eyebrow}>Still have a question?</p><h2>Talk with Stonegate before sharing more information.</h2></div>
        <a className={styles.primaryAction} href={siteConfig.phoneHref}><Phone size={17} aria-hidden="true" /> Call {siteConfig.phoneDisplay}</a>
      </section>
      <p className={styles.disclosure}>{directOfferDisclosure}</p>
      <PublicSiteFooter />
    </main>
  );
}
