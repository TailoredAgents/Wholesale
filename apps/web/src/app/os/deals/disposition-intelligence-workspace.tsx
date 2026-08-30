import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock3,
  DollarSign,
  Filter,
  Gauge,
  Info,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  Target,
  UsersRound,
} from "lucide-react";
import Link from "next/link";

import type {
  DispositionIntelligenceFilterOption,
  DispositionIntelligenceQuery,
  DispositionIntelligenceResponse,
  DispositionIntelligenceState,
} from "../../lib/api";
import { StatusBadge } from "../_components/design-system";
import styles from "./disposition-intelligence.module.css";

const deskLinks = [
  { key: "today", label: "Today" },
  { key: "active_deals", label: "Active Deals" },
  { key: "buyer_follow_ups", label: "Buyer Follow-ups" },
  { key: "replies", label: "Replies" },
  { key: "offers", label: "Offers" },
  { key: "deadlines", label: "Deadlines" },
] as const;

const activityMetrics = [
  ["Disposition cases", "cases"],
  ["Packages approved", "packages_approved"],
  ["Outreach sent", "outreach_sent"],
  ["Replies", "replies"],
  ["Inquiries", "inquiries"],
  ["Showings", "showings"],
  ["Offers", "offers"],
  ["Selected buyers", "selected_buyers"],
  ["Deposits", "deposits"],
] as const;

function stateLabel(state: DispositionIntelligenceState) {
  return `${state.charAt(0).toUpperCase()}${state.slice(1)}`;
}

function stateTone(state: DispositionIntelligenceState) {
  if (state === "known") return "success" as const;
  if (state === "partial") return "warning" as const;
  if (state === "unavailable") return "danger" as const;
  return "danger" as const;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatCurrency(value: number | null, state: DispositionIntelligenceState, visible = true) {
  if (!visible) return "Restricted";
  if (state === "unavailable" || value === null) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value / 100);
}

function formatHours(value: number | null, state: DispositionIntelligenceState) {
  if (state === "unavailable" || value === null) return "Unavailable";
  if (value < 1) return `${Math.round(value * 60)} min`;
  if (value < 48) return `${value.toFixed(value < 10 ? 1 : 0)} hr`;
  return `${(value / 24).toFixed(1)} days`;
}

function formatRate(value: number | null, state: DispositionIntelligenceState) {
  if (state === "unavailable" || value === null) return "Unavailable";
  return `${value.toFixed(1)}%`;
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Timestamp unavailable";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function optionValue(option: DispositionIntelligenceFilterOption) {
  return option.value;
}

function FilterSelect({
  defaultValue,
  label,
  name,
  options,
}: {
  defaultValue?: string;
  label: string;
  name: keyof DispositionIntelligenceQuery;
  options: DispositionIntelligenceFilterOption[];
}) {
  return (
    <label>
      <span>{label}</span>
      <select defaultValue={defaultValue ?? ""} name={name}>
        <option value="">All {label.toLowerCase()}</option>
        {options.map((option) => {
          const value = optionValue(option);
          return <option key={`${name}-${value}`} value={value}>{option.label} ({formatNumber(option.count)})</option>;
        })}
      </select>
    </label>
  );
}

function StateValue({
  state,
  value,
}: {
  state: DispositionIntelligenceState;
  value: number;
}) {
  if (state === "unavailable") return <>Unavailable</>;
  return <>{formatNumber(value)}</>;
}

export function DispositionIntelligenceWorkspace({
  apiConnected,
  data,
  errorMessage,
  filters,
}: {
  apiConnected: boolean;
  data: DispositionIntelligenceResponse | null;
  errorMessage: string | null;
  filters: DispositionIntelligenceQuery;
}) {
  if (!apiConnected || !data) {
    return (
      <section className={styles.unavailable} role="alert">
        <AlertTriangle aria-hidden="true" size={28} />
        <h2>Disposition performance is unavailable</h2>
        <p>{errorMessage ?? "Stonegate could not load the canonical disposition intelligence report."}</p>
        <div>
          <Link className={styles.primaryLink} href="/os/deals?view=disposition&desk=performance">Retry report</Link>
          <Link className={styles.secondaryLink} href="/os/deals?view=disposition&desk=today">Open today&apos;s desk</Link>
        </div>
      </section>
    );
  }

  const state = data.data_state;
  const privateEconomics = data.access.private_economics_visible;

  return (
    <section aria-label="Disposition performance intelligence" className={styles.workspace}>
      <header className={styles.hero}>
        <div>
          <span>Governed performance intelligence</span>
          <h2>Disposition performance</h2>
          <p>Measure completed outcomes, buyer movement, cycle time, source quality, and correction signals from Stonegate&apos;s canonical records.</p>
        </div>
        <div className={styles.generatedAt}>
          <Clock3 aria-hidden="true" size={17} />
          <span>Generated</span>
          <time dateTime={data.generated_at}>{formatDateTime(data.generated_at)}</time>
        </div>
      </header>

      <nav aria-label="Disposition desk views" className={styles.viewTabs}>
        {deskLinks.map((item) => (
          <Link href={`/os/deals?view=disposition&desk=${item.key}&scope=team`} key={item.key}>{item.label}</Link>
        ))}
        <Link aria-current="page" className={styles.activeView} href="/os/deals?view=disposition&desk=performance">Performance</Link>
      </nav>

      <div className={styles.stateBanner} data-state={state} role="status">
        {state === "known" ? <CheckCircle2 aria-hidden="true" size={19} /> : <AlertTriangle aria-hidden="true" size={19} />}
        <div>
          <strong>{state === "known" ? "Canonical outcome data is ready" : state === "partial" ? "Some outcome evidence is incomplete" : "Outcome evidence is unavailable"}</strong>
          <span>
            {state === "known"
              ? "Metrics below were reconciled from approved packages, outreach, offers, selections, and completed-deal ledgers."
              : state === "partial"
                ? "Use the evidence state beside each metric; missing evidence is never treated as zero."
                : "Filters returned no usable canonical evidence. Adjust the scope or review data-quality details."}
          </span>
        </div>
        <StatusBadge tone={stateTone(state)}>{stateLabel(state)}</StatusBadge>
      </div>

      <form action="/os/deals" className={styles.filters} method="get">
        <input name="view" type="hidden" value="disposition" />
        <input name="desk" type="hidden" value="performance" />
        <header>
          <div>
            <Filter aria-hidden="true" size={18} />
            <div><strong>Report filters</strong><span>Narrow the canonical evidence without changing operational records.</span></div>
          </div>
          <Link href="/os/deals?view=disposition&desk=performance">Clear filters</Link>
        </header>
        <div className={styles.filterGrid}>
          <label>
            <span>Start date</span>
            <input defaultValue={filters.start_at ?? ""} name="start_at" type="date" />
          </label>
          <label>
            <span>End date</span>
            <input defaultValue={filters.end_at ?? ""} name="end_at" type="date" />
          </label>
          <FilterSelect defaultValue={filters.deal_id} label="Deals" name="deal_id" options={data.filter_options.deals} />
          <FilterSelect defaultValue={filters.buyer_id} label="Buyers" name="buyer_id" options={data.filter_options.buyers} />
          <FilterSelect defaultValue={filters.agent_user_id} label="Agents" name="agent_user_id" options={data.filter_options.agents} />
          <FilterSelect defaultValue={filters.source} label="Sources" name="source" options={data.filter_options.sources} />
          <FilterSelect defaultValue={filters.market} label="Markets" name="market" options={data.filter_options.markets} />
          <FilterSelect defaultValue={filters.asset_class} label="Asset classes" name="asset_class" options={data.filter_options.asset_classes} />
        </div>
        <button type="submit">Apply filters</button>
      </form>

      <section aria-labelledby="outcomes-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Outcome evidence</span><h2 id="outcomes-heading">Start with completed business results</h2><p>Private economics remain permission-gated; operational counts stay visible to the disposition desk.</p></div>
          <DollarSign aria-hidden="true" size={23} />
        </header>
        {!privateEconomics ? (
          <div className={styles.restrictedNotice} role="note">
            <LockKeyhole aria-hidden="true" size={18} />
            <span>Revenue, spread, profit, and cost details are restricted for this account. Counts and workflow outcomes remain available.</span>
          </div>
        ) : null}
        <div className={styles.outcomeGrid}>
          <article className={styles.metricCard}>
            <span>Completed assignments</span>
            <strong><StateValue state={data.economics.state} value={data.economics.reconciled_completed_assignments} /></strong>
            <small>{stateLabel(data.economics.state)} evidence. {data.economics.completed_assignments === data.economics.reconciled_completed_assignments ? "Reconciled completed disposition outcomes" : `${formatNumber(data.economics.completed_assignments)} completion records before reconciliation`}</small>
          </article>
          <article className={styles.metricCard}>
            <span>Collected revenue</span>
            <strong>{formatCurrency(data.economics.collected_revenue_cents, data.economics.state, privateEconomics)}</strong>
            <small>{stateLabel(data.economics.state)} evidence. Collected, not projected, assignment revenue</small>
          </article>
          <article className={styles.metricCard}>
            <span>Approved company profit</span>
            <strong>{formatCurrency(data.economics.approved_company_profit_cents, data.economics.state, privateEconomics)}</strong>
            <small>{stateLabel(data.economics.state)} evidence. Finance-approved company profit</small>
          </article>
          <article className={styles.metricCard}>
            <span>Cost per completed assignment</span>
            <strong>{formatCurrency(data.economics.cost_per_completed_assignment_cents, data.economics.state, privateEconomics)}</strong>
            <small>{stateLabel(data.economics.state)} evidence. Recorded campaign cost divided by completed assignments</small>
          </article>
        </div>
        <details className={styles.metricDetails}>
          <summary>More governed economics</summary>
          <dl>
            <div><dt>Contracted assignment spread</dt><dd>{formatCurrency(data.economics.contracted_assignment_spread_cents, data.economics.state, privateEconomics)}</dd></div>
            <div><dt>Recorded campaign cost</dt><dd>{formatCurrency(data.economics.campaign_cost_cents, data.economics.state, privateEconomics)}</dd></div>
            <div><dt>Cost per offer</dt><dd>{formatCurrency(data.economics.cost_per_offer_cents, data.economics.state, privateEconomics)}</dd></div>
            <div><dt>Cost per selected buyer</dt><dd>{formatCurrency(data.economics.cost_per_selected_buyer_cents, data.economics.state, privateEconomics)}</dd></div>
          </dl>
          <p>{data.economics.detail}</p>
        </details>
      </section>

      <section aria-labelledby="flow-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Cycle and conversion</span><h2 id="flow-heading">Where deals move or stall</h2><p>Time-to-milestone and rate evidence use explicit denominators and evidence states.</p></div>
          <Target aria-hidden="true" size={23} />
        </header>
        <div className={styles.tableWrap} role="region" aria-label="Disposition milestone timing" tabIndex={0}>
          <table>
            <thead><tr><th scope="col">Milestone</th><th scope="col">Reached</th><th scope="col">Median</th><th scope="col">90th percentile</th><th scope="col">Evidence</th></tr></thead>
            <tbody>
              {data.milestones.length ? data.milestones.map((item) => (
                <tr key={item.key}>
                  <th scope="row">{item.label}</th>
                  <td><StateValue state={item.state} value={item.count} /></td>
                  <td>{formatHours(item.median_hours, item.state)}</td>
                  <td>{formatHours(item.p90_hours, item.state)}</td>
                  <td><StatusBadge tone={stateTone(item.state)}>{stateLabel(item.state)}</StatusBadge></td>
                </tr>
              )) : <tr><td className={styles.emptyCell} colSpan={5}>No milestone evidence is available for this scope.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className={styles.rateGrid}>
          {data.rates.length ? data.rates.map((item) => (
            <article className={styles.rateCard} data-state={item.state} key={item.key}>
              <span>{item.label}</span>
              <strong>{formatRate(item.rate_percent, item.state)}</strong>
              <small>{item.state === "known" || item.state === "partial" ? `${formatNumber(item.numerator)} of ${formatNumber(item.denominator)} eligible records. ${stateLabel(item.state)} evidence` : stateLabel(item.state)}</small>
            </article>
          )) : <p className={styles.emptyMessage}>No conversion rates are available for this scope.</p>}
        </div>
      </section>

      <section aria-labelledby="activity-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Workflow activity</span><h2 id="activity-heading">Volume behind the outcomes</h2><p>Activity explains throughput; it is not presented as business success by itself.</p></div>
          <Gauge aria-hidden="true" size={23} />
        </header>
        <div className={styles.activityGrid}>
          {activityMetrics.map(([label, key]) => (
            <article key={key}><span>{label}</span><strong>{state === "unavailable" ? "Unavailable" : formatNumber(data.activity[key])}</strong><small>{stateLabel(state)} evidence</small></article>
          ))}
        </div>
      </section>

      <section aria-labelledby="sources-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Source performance</span><h2 id="sources-heading">Which buyer channels produce outcomes</h2><p>Source labels come from saved buyer and outreach attribution, not inferred browsing behavior.</p></div>
          <BarChart3 aria-hidden="true" size={23} />
        </header>
        <div className={styles.tableWrap} role="region" aria-label="Disposition source performance" tabIndex={0}>
          <table>
            <thead><tr><th scope="col">Source</th><th scope="col">Activity</th><th scope="col">Offers</th><th scope="col">Selections</th><th scope="col">Completed</th><th scope="col">Collected revenue</th><th scope="col">Evidence</th></tr></thead>
            <tbody>
              {data.sources.length ? data.sources.map((row) => (
                <tr key={row.key}>
                  <th scope="row"><strong>{row.label}</strong><small>{row.category}</small></th>
                  <td><StateValue state={row.state} value={row.activity_count} /></td>
                  <td><StateValue state={row.state} value={row.offers} /></td>
                  <td><StateValue state={row.state} value={row.selected_buyers} /></td>
                  <td><StateValue state={row.state} value={row.completed_assignments} /></td>
                  <td>{formatCurrency(row.collected_revenue_cents, row.state, privateEconomics)}</td>
                  <td><StatusBadge tone={stateTone(row.state)}>{stateLabel(row.state)}</StatusBadge></td>
                </tr>
              )) : <tr><td className={styles.emptyCell} colSpan={7}>No source evidence is available for this scope.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="buyers-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Buyer performance</span><h2 id="buyers-heading">Reliability backed by recorded outcomes</h2><p>Scores include saved buyer behavior and provenance; missing evidence stays unavailable.</p></div>
          <UsersRound aria-hidden="true" size={23} />
        </header>
        <div className={styles.tableWrap} role="region" aria-label="Buyer reliability performance" tabIndex={0}>
          <table>
            <thead><tr><th scope="col">Buyer</th><th scope="col">Replies</th><th scope="col">Showings</th><th scope="col">Offers</th><th scope="col">Selections</th><th scope="col">Completed</th><th scope="col">Fallouts / retrades</th><th scope="col">Reliability</th><th scope="col">Evidence</th></tr></thead>
            <tbody>
              {data.buyers.length ? data.buyers.map((row) => (
                <tr key={row.buyer_id}>
                  <th scope="row"><Link href={`/os/buyers?buyer=${row.buyer_id}`}>{row.name}</Link><small>{row.provenance}</small></th>
                  <td><StateValue state={row.state} value={row.replies} /></td>
                  <td><StateValue state={row.state} value={row.showings} /></td>
                  <td><StateValue state={row.state} value={row.offers} /></td>
                  <td><StateValue state={row.state} value={row.selections} /></td>
                  <td><StateValue state={row.state} value={row.completed_assignments} /></td>
                  <td><StateValue state={row.state} value={row.fallouts + row.retrades} /></td>
                  <td>{row.state === "unavailable" || row.reliability_score_basis_points === null ? "Unavailable" : `${(row.reliability_score_basis_points / 100).toFixed(0)} / 100`}</td>
                  <td><StatusBadge tone={stateTone(row.state)}>{stateLabel(row.state)}</StatusBadge></td>
                </tr>
              )) : <tr><td className={styles.emptyCell} colSpan={9}>No buyer outcome evidence is available for this scope.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="agents-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Agent operations</span><h2 id="agents-heading">Human work tied to disposition outcomes</h2><p>These are recorded workflow actions, not causal claims about individual performance.</p></div>
          <ShieldCheck aria-hidden="true" size={23} />
        </header>
        <div className={styles.tableWrap} role="region" aria-label="Disposition agent activity" tabIndex={0}>
          <table>
            <thead><tr><th scope="col">Agent</th><th scope="col">Packages</th><th scope="col">Outreach</th><th scope="col">Replies reviewed</th><th scope="col">Selections approved</th><th scope="col">Outcomes recorded</th><th scope="col">Completed</th><th scope="col">Evidence</th></tr></thead>
            <tbody>
              {data.agents.length ? data.agents.map((row) => (
                <tr key={row.user_id}>
                  <th scope="row"><strong>{row.name}</strong><small>{row.role}</small></th>
                  <td><StateValue state={row.state} value={row.packages_approved} /></td>
                  <td><StateValue state={row.state} value={row.outreach_sent} /></td>
                  <td><StateValue state={row.state} value={row.replies_reviewed} /></td>
                  <td><StateValue state={row.state} value={row.selections_approved} /></td>
                  <td><StateValue state={row.state} value={row.outcomes_recorded} /></td>
                  <td><StateValue state={row.state} value={row.completed_assignments} /></td>
                  <td><StatusBadge tone={stateTone(row.state)}>{stateLabel(row.state)}</StatusBadge></td>
                </tr>
              )) : <tr><td className={styles.emptyCell} colSpan={8}>No agent workflow evidence is available for this scope.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="learning-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Learning and corrections</span><h2 id="learning-heading">Improve the system without overstating AI impact</h2><p>Human-led and AI-assisted counts are descriptive cohorts. They do not prove that assistance caused an outcome.</p></div>
          <Sparkles aria-hidden="true" size={23} />
        </header>
        <div className={styles.learningGrid}>
          <article><span>Human-led records</span><strong><StateValue state={data.learning.state} value={data.learning.human_led_count} /></strong><small>{stateLabel(data.learning.state)} evidence</small></article>
          <article><span>AI-assisted records</span><strong><StateValue state={data.learning.state} value={data.learning.ai_assisted_count} /></strong><small>{stateLabel(data.learning.state)} evidence</small></article>
          <article><span>Minimum comparison sample</span><strong>{formatNumber(data.learning.minimum_comparison_sample)}</strong><small>Governed comparison threshold</small></article>
          <article><span>Comparison readiness</span><strong>{data.learning.comparison_allowed ? "Ready" : "Not enough evidence"}</strong><small>{stateLabel(data.learning.state)} evidence</small></article>
        </div>
        <div className={styles.learningNotice} role="note"><Info aria-hidden="true" size={18} /><span>{data.learning.notice}</span></div>
        <dl className={styles.correctionGrid}>
          <div><dt>Package revisions</dt><dd>{formatNumber(data.learning.corrections.package_revisions)}</dd></div>
          <div><dt>Match overrides</dt><dd>{formatNumber(data.learning.corrections.match_overrides)}</dd></div>
          <div><dt>AI corrections</dt><dd>{formatNumber(data.learning.corrections.ai_corrections)}</dd></div>
          <div><dt>Backup-buyer saves</dt><dd>{formatNumber(data.learning.corrections.backup_buyer_saves)}</dd></div>
        </dl>
        <p className={styles.correctionHelp}>Corrections remain governed in their source workflows. This report reads the immutable revision, override, and outcome ledgers; it does not rewrite history.</p>
      </section>

      <section aria-labelledby="quality-heading" className={styles.section}>
        <header className={styles.sectionHeader}>
          <div><span>Definitions and provenance</span><h2 id="quality-heading">Know what each number can support</h2><p>Open any metric definition before using it in a management decision.</p></div>
          <Info aria-hidden="true" size={23} />
        </header>
        <div className={styles.qualityGrid}>
          {data.data_quality.length ? data.data_quality.map((item) => (
            <article data-state={item.state} key={item.key}>
              <header><strong>{item.label}</strong><StatusBadge tone={stateTone(item.state)}>{stateLabel(item.state)}</StatusBadge></header>
              <p>{item.detail}</p>
              <small>{formatNumber(item.record_count)} supporting record{item.record_count === 1 ? "" : "s"}</small>
            </article>
          )) : <p className={styles.emptyMessage}>No data-quality signals are available for this scope.</p>}
        </div>
        <div className={styles.provenanceList}>
          {data.provenance.length ? data.provenance.map((item) => (
            <details key={item.metric_key}>
              <summary><span>{item.metric_key.replaceAll("_", " ")}</span><StatusBadge tone={stateTone(item.state)}>{stateLabel(item.state)}</StatusBadge></summary>
              <p>{item.definition}</p>
              <small>Canonical sources: {item.canonical_sources.length ? item.canonical_sources.join(", ") : "No canonical source recorded"}</small>
            </details>
          )) : <p className={styles.emptyMessage}>No metric provenance is available for this scope.</p>}
        </div>
      </section>
    </section>
  );
}
