"use client";

import { Bot, ChevronRight, ShieldCheck, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { Drawer } from "./design-system";
import styles from "./copilot-launcher.module.css";

export function CopilotLauncher({
  attentionCount = 0,
  children,
  description,
  name,
  placement = "inline",
  score,
  summary,
  triggerLabel,
}: {
  attentionCount?: number;
  children: ReactNode;
  description: string;
  name: string;
  placement?: "header" | "inline";
  score?: number | null;
  summary?: string;
  triggerLabel?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      {placement === "header" ? (
        <button
          aria-haspopup="dialog"
          className={styles.headerTrigger}
          onClick={() => setOpen(true)}
          type="button"
        >
          <Sparkles aria-hidden="true" size={15} />
          <span>{name}</span>
          {attentionCount ? <strong>{attentionCount}</strong> : null}
        </button>
      ) : (
        <section className={styles.launcher} data-attention={attentionCount ? "true" : "false"}>
          <span className={styles.icon}><Bot aria-hidden="true" size={18} /></span>
          <div className={styles.copy}>
            <span>{name}</span>
            <strong>{summary ?? "AI assistance is ready for this workspace."}</strong>
            <small>{description}</small>
          </div>
          <div className={styles.status}>
            {score !== null && score !== undefined ? (
              <span><strong>{score}</strong>/100</span>
            ) : null}
            <span>
              <ShieldCheck aria-hidden="true" size={14} />
              Review required
            </span>
          </div>
          <button aria-haspopup="dialog" onClick={() => setOpen(true)} type="button">
            <span>{triggerLabel ?? "Open copilot"}</span>
            {attentionCount ? <strong>{attentionCount}</strong> : null}
            <ChevronRight aria-hidden="true" size={16} />
          </button>
        </section>
      )}

      <Drawer
        description={description}
        onClose={() => setOpen(false)}
        open={open}
        size="wide"
        title={name}
      >
        <div className={styles.drawerContext}>
          <span><ShieldCheck aria-hidden="true" size={14} />Governed assistance</span>
          <p>
            Recommendations remain drafts until a staff member accepts, corrects, or rejects them.
          </p>
        </div>
        <div className={styles.drawerBody}>{children}</div>
      </Drawer>
    </>
  );
}
