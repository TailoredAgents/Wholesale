import { ArrowRight, Check, Clock3, Hammer, HeartHandshake, House, Phone } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { AddressOfferStart } from "./address-offer-start";
import { PublicConversionTracker } from "./public-conversion-tracker";
import { PublicSiteFooter } from "./public-site-footer";
import { PublicSiteHeader } from "./public-site-header";
import { sellerSituations } from "./seller-situations";
import { directOfferDisclosure, siteConfig } from "./site-config";
import styles from "./page.module.css";

const processSteps = [
  {
    title: "Share the property",
    detail: "Start with the address. We will ask about condition, occupancy, timing, and your goals.",
  },
  {
    title: "Review your options",
    detail: "A Stonegate team member reviews the property and explains how a direct offer is calculated.",
  },
  {
    title: "Choose what fits",
    detail: "If we make an offer, you can accept, decline, or compare it with listing and repair options.",
  },
];

const situationIcons = [HeartHandshake, Hammer, Clock3];

const comparisonRows = [
  { label: "Property condition", direct: "Sell as-is", listing: "Repairs or prep may help" },
  { label: "Showings", direct: "Not part of our process", listing: "Usually expected" },
  { label: "Agent commission", direct: "None paid to Stonegate", listing: "May apply" },
  { label: "Potential price", direct: "Typically below retail value", listing: "May pursue retail value" },
  { label: "Timeline", direct: "Set by written agreement", listing: "Depends on buyer and financing" },
];

export default function PublicHomePage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteConfig.siteUrl}/#organization`,
        name: siteConfig.name,
        url: siteConfig.siteUrl,
        telephone: "+1-678-541-7725",
        areaServed: { "@type": "State", name: "Georgia" },
      },
      {
        "@type": "WebSite",
        "@id": `${siteConfig.siteUrl}/#website`,
        url: siteConfig.siteUrl,
        name: siteConfig.name,
        publisher: { "@id": `${siteConfig.siteUrl}/#organization` },
      },
    ],
  };

  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: "home" }} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <PublicSiteHeader />

      <section className={styles.hero} aria-labelledby="home-title">
        <Image
          className={styles.heroImage}
          src="/images/stonegate-georgia-home-hero.jpg"
          alt="Red-brick Georgia home surrounded by mature trees"
          fill
          loading="eager"
          fetchPriority="high"
          quality={60}
          sizes="100vw"
        />
        <div className={styles.heroOverlay} />
        <div className={styles.heroInner}>
          <p className={styles.heroEyebrow}>A direct home sale option in Georgia</p>
          <h1 id="home-title">Sell your Georgia house as-is for a direct cash offer.</h1>
          <p className={styles.heroLead}>
            Skip repairs, listing prep, and showings. Start with the address, understand the
            tradeoffs, and decide whether Stonegate fits your situation.
          </p>
          <AddressOfferStart />
          <div className={styles.heroContact}>
            <a href={siteConfig.phoneHref}>
              <Phone size={17} aria-hidden="true" />
              Prefer to talk? {siteConfig.phoneDisplay}
            </a>
            <span>Georgia-focused property review</span>
          </div>
        </div>
      </section>

      <section className={styles.assurance} aria-label="Stonegate offer request assurances">
        <div>
          <Check size={19} aria-hidden="true" />
          <span><strong>No obligation</strong> to accept an offer</span>
        </div>
        <div>
          <Hammer size={19} aria-hidden="true" />
          <span><strong>No repairs</strong> required before review</span>
        </div>
        <div>
          <House size={19} aria-hidden="true" />
          <span><strong>No showings</strong> in our direct process</span>
        </div>
      </section>

      <section className={styles.introSection}>
        <div className={styles.sectionLabel}>A clear option</div>
        <div className={styles.introCopy}>
          <h2>A home sale should start with the truth about your choices.</h2>
          <p>
            A direct cash offer is built for convenience and certainty, not the highest possible
            sale price. Stonegate explains the property review, offer assumptions, and next steps
            so you can compare the direct path with listing, repairing, or waiting.
          </p>
          <Link className={styles.textLink} href="/how-it-works">
            See exactly how the process works <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className={styles.processSection}>
        <div className={styles.sectionHeading}>
          <p>How it works</p>
          <h2>Three practical steps. You stay in control.</h2>
        </div>
        <div className={styles.processGrid}>
          {processSteps.map((step, index) => (
            <article key={step.title}>
              <span>{index + 1}</span>
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.situationsSection} id="selling-situations">
        <div className={styles.sectionHeading}>
          <p>Selling situations</p>
          <h2>Built for properties and timelines that need a simpler path.</h2>
        </div>
        <div className={styles.situationGrid}>
          {sellerSituations.map((situation, index) => {
            const Icon = situationIcons[index];
            return (
              <article key={situation.slug}>
                <div className={styles.situationImage}>
                  <Image src={situation.image} alt={situation.imageAlt} fill quality={60} sizes="(max-width: 760px) 100vw, 33vw" />
                </div>
                <div className={styles.situationBody}>
                  <Icon size={20} aria-hidden="true" />
                  <p>{situation.eyebrow}</p>
                  <h3>{situation.shortTitle}</h3>
                  <span>{situation.description}</span>
                  <Link href={`/${situation.slug}`}>
                    Explore this situation <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className={styles.comparisonSection}>
        <div className={styles.comparisonCopy}>
          <p className={styles.sectionKicker}>Compare the paths</p>
          <h2>A direct offer trades some potential price for a simpler sale.</h2>
          <p>
            Neither path is automatically better. The right choice depends on condition, time,
            available cash for repairs, and how much uncertainty you can carry.
          </p>
        </div>
        <div className={styles.comparisonTable} role="table" aria-label="Direct offer and traditional listing comparison">
          <div className={styles.comparisonHeader} role="row">
            <span role="columnheader">Consideration</span>
            <strong role="columnheader">Stonegate direct offer</strong>
            <strong role="columnheader">Traditional listing</strong>
          </div>
          {comparisonRows.map((row) => (
            <div className={styles.comparisonRow} role="row" key={row.label}>
              <span role="cell">{row.label}</span>
              <strong role="cell">{row.direct}</strong>
              <span role="cell">{row.listing}</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.localSection}>
        <div>
          <p className={styles.sectionKicker}>Local starting point</p>
          <h2>Serving Georgia property owners, beginning in metro Atlanta.</h2>
        </div>
        <div>
          <p>
            Stonegate is building a Georgia-focused acquisitions operation with a real person
            reviewing each seller inquiry. We only discuss properties in areas our team can
            responsibly evaluate.
          </p>
          <Link className={styles.textLink} href="/about">
            Learn about Stonegate <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className={styles.finalCta}>
        <div>
          <p>Start with the property</p>
          <h2>See whether a direct offer fits your situation.</h2>
        </div>
        <AddressOfferStart compact />
      </section>

      <p className={styles.homeDisclosure}>{directOfferDisclosure}</p>
      <PublicSiteFooter />
    </main>
  );
}
