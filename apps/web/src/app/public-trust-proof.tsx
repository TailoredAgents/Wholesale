import { ExternalLink, Quote, Star } from "lucide-react";

import { getPublicTrustProof, type PublicTrustProof as Proof } from "./lib/api";
import styles from "./public-trust-proof.module.css";

function formatDate(value: string | null) {
  if (!value) return null;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function sourceLabel(sourceType: string) {
  const labels: Record<string, string> = {
    google_review: "Original Google review",
    signed_release: "Shared with written permission",
    seller_permission: "Shared with seller permission",
    transaction_record: "Verified Stonegate transaction record",
    accounting_record: "Verified Stonegate accounting record",
    other: "Verified source",
  };
  return labels[sourceType] ?? "Verified source";
}

function ProofSource({ proof }: { proof: Proof }) {
  const label = sourceLabel(proof.source_type);
  return proof.source_url ? (
    <a href={proof.source_url} rel="noreferrer noopener" target="_blank">
      {label} <ExternalLink size={13} aria-hidden="true" />
    </a>
  ) : (
    <span>{label}</span>
  );
}

export async function PublicTrustProof() {
  const records = await getPublicTrustProof();
  if (!records.length) return null;

  const statistics = records.filter((record) => record.proof_type === "statistic").slice(0, 4);
  const reviews = records.filter((record) => record.proof_type === "review").slice(0, 3);
  const stories = records
    .filter((record) =>
      ["seller_story", "completed_purchase"].includes(record.proof_type),
    )
    .slice(0, 3);

  return (
    <section className={styles.proofSection} data-public-proof="true">
      <div className={styles.heading}>
        <p>Verified Stonegate proof</p>
        <h2>Real outcomes and experiences, published only with supporting evidence.</h2>
      </div>

      {statistics.length ? (
        <div className={styles.statistics} aria-label="Verified Stonegate results">
          {statistics.map((proof) => (
            <article key={proof.id}>
              <strong>{proof.metric_value}</strong>
              <h3>{proof.metric_label}</h3>
              <p>
                {proof.as_of_date ? `As of ${formatDate(proof.as_of_date)}. ` : null}
                {proof.methodology}
              </p>
              <ProofSource proof={proof} />
              {proof.disclosure ? <small>{proof.disclosure}</small> : null}
            </article>
          ))}
        </div>
      ) : null}

      {reviews.length ? (
        <div className={styles.reviewArea}>
          <div className={styles.reviewIntro}>
            <Quote size={26} aria-hidden="true" />
            <div>
              <p>Seller experiences</p>
              <h3>Words Stonegate has permission to share</h3>
            </div>
          </div>
          <div className={styles.reviews}>
            {reviews.map((proof) => (
              <figure key={proof.id}>
                {proof.rating ? (
                  <div
                    className={styles.rating}
                    aria-label={`${proof.rating} out of 5 stars`}
                    role="img"
                  >
                    {Array.from({ length: proof.rating }, (_, index) => (
                      <Star key={index} size={15} fill="currentColor" aria-hidden="true" />
                    ))}
                  </div>
                ) : null}
                <blockquote>&ldquo;{proof.content}&rdquo;</blockquote>
                <figcaption>
                  <strong>{proof.attribution_name}</strong>
                  <span>
                    {[proof.attribution_detail, proof.location_label]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </figcaption>
                <ProofSource proof={proof} />
                {proof.disclosure ? <small>{proof.disclosure}</small> : null}
              </figure>
            ))}
          </div>
        </div>
      ) : null}

      {stories.length ? (
        <div className={styles.stories}>
          <div className={styles.storyHeading}>
            <p>Documented seller outcomes</p>
            <h3>What the direct-sale process looked like in practice</h3>
          </div>
          <div>
            {stories.map((proof) => (
              <article key={proof.id}>
                <div>
                  <span>
                    {proof.proof_type === "completed_purchase"
                      ? "Completed purchase"
                      : "Seller story"}
                  </span>
                  <h4>{proof.title}</h4>
                  {proof.content ? <p>{proof.content}</p> : null}
                </div>
                <aside>
                  <strong>{proof.location_label ?? proof.attribution_detail ?? "Georgia"}</strong>
                  {proof.as_of_date ? <span>{formatDate(proof.as_of_date)}</span> : null}
                  <ProofSource proof={proof} />
                  {proof.disclosure ? <small>{proof.disclosure}</small> : null}
                </aside>
              </article>
            ))}
          </div>
        </div>
      ) : null}

      <p className={styles.context}>
        These are individual records, not a promise that another property will receive the same
        result. Every property and seller situation is reviewed separately.
      </p>
    </section>
  );
}
