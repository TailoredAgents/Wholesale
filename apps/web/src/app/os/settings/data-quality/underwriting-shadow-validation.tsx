import { FlaskConical, Gauge, GitCompareArrows, ShieldCheck } from "lucide-react";
import Link from "next/link";

import type { UnderwritingShadowValidation } from "../../../lib/api";
import { StatusBadge } from "../../_components/design-system";
import { labelize } from "../../os-utils";
import styles from "./underwriting-shadow-validation.module.css";

function percent(value: number | null, signed = false) {
  if (value === null) return "--";
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function gateTone(status: string): "success" | "warning" | "danger" {
  if (status === "passed") return "success";
  if (status === "pending") return "warning";
  return "danger";
}

function winnerLabel(value: string) {
  if (value === "v3_shadow") return "V3 shadow";
  if (value === "v2.2") return "V2.2";
  return "Tie";
}

export function UnderwritingShadowValidationPanel({
  validation,
}: {
  validation: UnderwritingShadowValidation;
}) {
  const overall = validation.overall;
  const passedGates = validation.gates.filter((gate) => gate.status === "passed").length;

  return (
    <section className={styles.workspace} aria-labelledby="shadow-validation-title">
      <header>
        <div>
          <span>U3.10 controlled rollout</span>
          <h3 id="shadow-validation-title">V2.2 versus V3 shadow validation</h3>
        </div>
        <StatusBadge tone={validation.activation_allowed ? "success" : "warning"}>
          {labelize(validation.rollout_status)}
        </StatusBadge>
      </header>

      <div className={styles.authorityNotice}>
        <ShieldCheck size={18} />
        <div>
          <strong>{validation.active_methodology_version} remains the live method</strong>
          <span>
            V3 is comparison-only. Offers, contracts, and methodology activation remain human-controlled.
          </span>
        </div>
      </div>

      <div className={styles.metrics} aria-label="Shadow replay performance">
        <div><FlaskConical size={17} /><span>Paired outcomes</span><strong>{overall.paired_case_count} / 50</strong></div>
        <div><Gauge size={17} /><span>V2.2 median error</span><strong>{percent(overall.baseline_median_absolute_error_percentage)}</strong></div>
        <div><Gauge size={17} /><span>V3 shadow error</span><strong>{percent(overall.shadow_median_absolute_error_percentage)}</strong></div>
        <div><GitCompareArrows size={17} /><span>Shadow improvement</span><strong>{percent(overall.median_improvement_percentage_points, true)}</strong></div>
      </div>

      <div className={styles.sectionHeader}>
        <div><span>Activation gates</span><h4>Controlled-rollout readiness</h4></div>
        <strong>{passedGates} / {validation.gates.length} passed</strong>
      </div>
      <div className={styles.gates}>
        {validation.gates.map((gate) => (
          <article key={gate.key}>
            <div>
              <strong>{gate.label}</strong>
              <StatusBadge tone={gateTone(gate.status)}>{labelize(gate.status)}</StatusBadge>
            </div>
            <dl>
              <div><dt>Current</dt><dd>{gate.current_value}</dd></div>
              <div><dt>Required</dt><dd>{gate.required_value}</dd></div>
            </dl>
            <p>{gate.detail}</p>
          </article>
        ))}
      </div>

      <div className={styles.sectionHeader}>
        <div><span>Validation cohort</span><h4>Difficult-scenario coverage</h4></div>
        <strong>{Object.values(validation.scenario_coverage).filter((count) => count > 0).length} / {Object.keys(validation.scenario_coverage).length}</strong>
      </div>
      <div className={styles.scenarios}>
        {Object.entries(validation.scenario_coverage).map(([scenario, count]) => (
          <div key={scenario}>
            <span>{labelize(scenario)}</span>
            <strong>{count}</strong>
          </div>
        ))}
      </div>

      <div className={styles.sectionHeader}>
        <div><span>Paired replay ledger</span><h4>Case-by-case accuracy comparison</h4></div>
        <strong>{validation.cases.length} cases</strong>
      </div>
      <div className={styles.tableWrap} tabIndex={0}>
        <table>
          <thead>
            <tr><th>Property</th><th>Market</th><th>Scenarios</th><th>V2.2 error</th><th>V3 error</th><th>Difference</th><th>Closer</th><th>Risk</th></tr>
          </thead>
          <tbody>
            {validation.cases.length ? validation.cases.map((item) => (
              <tr key={item.analysis_id}>
                <td><Link href={`/os/leads/${item.lead_id}?tab=valuation`}>{item.property_address}</Link></td>
                <td>{item.market_key}</td>
                <td>{item.validation_scenarios.length ? item.validation_scenarios.map(labelize).join(", ") : "Unclassified"}</td>
                <td>{percent(item.baseline_absolute_error_percentage)}</td>
                <td>{percent(item.shadow_absolute_error_percentage)}</td>
                <td>{percent(item.improvement_percentage_points, true)}</td>
                <td><StatusBadge tone={item.winner === "v3_shadow" ? "success" : item.winner === "v2.2" ? "warning" : "neutral"}>{winnerLabel(item.winner)}</StatusBadge></td>
                <td>{item.risk_flags.length ? item.risk_flags.join(" ") : "No replay flags"}</td>
              </tr>
            )) : (
              <tr><td colSpan={8}>Save verified outcomes on analyses that contain a V3 shadow comparison.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
