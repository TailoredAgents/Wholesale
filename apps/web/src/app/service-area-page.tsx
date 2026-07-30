import { ArrowRight, Check, House, MapPin, Phone, SearchCheck } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { AddressOfferStart } from "./address-offer-start";
import { PublicConversionTracker } from "./public-conversion-tracker";
import { PublicSiteFooter } from "./public-site-footer";
import { PublicSiteHeader } from "./public-site-header";
import type { ServiceArea } from "./service-areas";
import { directOfferDisclosure, siteConfig } from "./site-config";
import styles from "./service-area.module.css";

type ServiceAreaPageProps = {
  area: ServiceArea;
};

export function ServiceAreaPage({ area }: ServiceAreaPageProps) {
  const pageUrl = `${siteConfig.siteUrl}/service-areas/${area.slug}`;
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebPage",
        "@id": `${pageUrl}/#webpage`,
        url: pageUrl,
        name: `${area.name} Home Buyers | ${siteConfig.name}`,
        description: area.description,
        isPartOf: { "@id": `${siteConfig.siteUrl}/#website` },
        about: { "@id": `${pageUrl}/#service` },
        breadcrumb: { "@id": `${pageUrl}/#breadcrumb` },
      },
      {
        "@type": "Service",
        "@id": `${pageUrl}/#service`,
        name: `Direct as-is home sale review in ${area.name}`,
        description: area.description,
        provider: { "@id": `${siteConfig.siteUrl}/#organization` },
        areaServed: {
          "@type": "Place",
          name: `${area.name}, Georgia`,
        },
        serviceType: "Direct as-is residential property purchase review",
        offers: {
          "@type": "Offer",
          description: "No-obligation property review request",
          price: "0",
          priceCurrency: "USD",
        },
      },
      {
        "@type": "BreadcrumbList",
        "@id": `${pageUrl}/#breadcrumb`,
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: "Home",
            item: siteConfig.siteUrl,
          },
          {
            "@type": "ListItem",
            position: 2,
            name: area.name,
            item: pageUrl,
          },
        ],
      },
    ],
  };

  return (
    <main className={styles.page}>
      <PublicConversionTracker metadata={{ page: `service-area-${area.slug}` }} />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <PublicSiteHeader />

      <nav className={styles.breadcrumbs} aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{area.name} service area</span>
      </nav>

      <section className={styles.hero} aria-labelledby="service-area-title">
        <Image
          className={styles.heroImage}
          src={area.image}
          alt={area.imageAlt}
          fill
          priority
          quality={65}
          sizes="100vw"
        />
        <div className={styles.heroOverlay} />
        <div className={styles.heroInner}>
          <p className={styles.eyebrow}>{area.eyebrow}</p>
          <h1 id="service-area-title">{area.title}</h1>
          <p>{area.description}</p>
          <AddressOfferStart compact inputId={`${area.slug}-hero-address`} />
          <a className={styles.phone} href={siteConfig.phoneHref}>
            <Phone size={17} aria-hidden="true" />
            Ask about your address: {siteConfig.phoneDisplay}
          </a>
        </div>
      </section>

      <section className={styles.coverageSection} aria-labelledby="coverage-title">
        <div>
          <p className={styles.eyebrow}>How coverage works</p>
          <h2 id="coverage-title">The address decides whether Stonegate can help.</h2>
          <p>
            A regional name is only a starting point. Stonegate reviews the specific location and
            current operating capacity before confirming the next step.
          </p>
        </div>
        <div className={styles.coverageList}>
          {area.coverageNotes.map((note) => (
            <div key={note}>
              <Check size={19} aria-hidden="true" />
              <span>{note}</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.reviewBand}>
        <div className={styles.reviewHeading}>
          <SearchCheck size={28} aria-hidden="true" />
          <span>
            <p className={styles.eyebrow}>Local property review</p>
            <h2>Location matters, but it is not the only number.</h2>
          </span>
        </div>
        <div className={styles.factorGrid}>
          {area.reviewFactors.map((factor) => (
            <div key={factor}>
              <MapPin size={18} aria-hidden="true" />
              <p>{factor}</p>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.situationsSection}>
        <div>
          <p className={styles.eyebrow}>Property situations</p>
          <h2>A direct sale can be useful when the property or timeline needs flexibility.</h2>
          <p>
            Stonegate reviews homes as-is. Explore the situations sellers commonly compare before
            deciding whether to repair, list, wait, or request a direct offer.
          </p>
        </div>
        <div className={styles.situationLinks}>
          <Link href="/sell-inherited-house">
            <House size={20} aria-hidden="true" />
            <span>
              <strong>Inherited property</strong>
              <small>Ownership, probate, belongings, and timing</small>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
          <Link href="/sell-house-needs-repairs">
            <House size={20} aria-hidden="true" />
            <span>
              <strong>Major repairs</strong>
              <small>Compare repairing, listing, or selling as-is</small>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
          <Link href="/sell-house-fast">
            <House size={20} aria-hidden="true" />
            <span>
              <strong>Flexible timeline</strong>
              <small>Understand what can affect a requested closing date</small>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className={styles.tradeoffSection}>
        <div>
          <p className={styles.eyebrow}>Compare before deciding</p>
          <h2>A simpler sale may produce less than a prepared retail listing.</h2>
        </div>
        <div>
          <p>
            A direct offer accounts for repairs, resale costs, time, and risk. Stonegate explains
            the assumptions so you can compare the offer with listing, repairing, or waiting.
          </p>
          <Link href="/how-it-works">
            See the complete process <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section className={styles.faqSection}>
        <div className={styles.sectionHeading}>
          <p className={styles.eyebrow}>{area.name} questions</p>
          <h2>What property owners commonly ask about coverage</h2>
        </div>
        <div className={styles.faqList}>
          {area.faqs.map((faq) => (
            <details key={faq.question}>
              <summary>{faq.question}</summary>
              <p>{faq.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className={styles.finalCta}>
        <div>
          <p className={styles.eyebrow}>Confirm the property</p>
          <h2>Start with the address. Keep the decision.</h2>
        </div>
        <AddressOfferStart compact inputId={`${area.slug}-final-address`} />
      </section>
      <p className={styles.disclosure}>{directOfferDisclosure}</p>
      <PublicSiteFooter />
    </main>
  );
}
