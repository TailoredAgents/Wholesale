"use client";

import { CalendarDays, Download, Inbox, MoreHorizontal, Plus, Search, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  Drawer,
  EmptyState,
  FormField,
  IconButton,
  Menu,
  SegmentedControl,
  Select,
  Skeleton,
  StatusBadge,
  TableShell,
  Tabs,
  TextArea,
  TextInput,
  Toast,
} from "../_components/design-system";
import {
  CalendarPageContract,
  ManagementPageContract,
  PageHeader,
  PipelinePageContract,
  QueuePageContract,
  RecordPageContract,
  RecordSummaryHeader,
  SectionPanel,
  StickyActionBar,
  WorkspacePage,
} from "../_components/page-contracts";
import styles from "./reference.module.css";

type Density = "comfortable" | "compact";
type RecordTab = "summary" | "activity" | "documents";
type Contract = "queue" | "record" | "pipeline" | "calendar" | "management";

const queueRows = ["Mary Johnson", "Robert Keller", "Denise Carter"];

function Placeholder({ children, strong = false }: { children: string; strong?: boolean }) {
  return <div className={strong ? styles.placeholderStrong : styles.placeholder}>{children}</div>;
}

export function DesignSystemReference() {
  const [density, setDensity] = useState<Density>("comfortable");
  const [tab, setTab] = useState<RecordTab>("summary");
  const [contract, setContract] = useState<Contract>("queue");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(true);

  return (
    <WorkspacePage>
      <PageHeader
        actions={
          <>
            <Button icon={<Download size={16} />} variant="secondary">Export</Button>
            <Button icon={<Plus size={16} />}>Create record</Button>
          </>
        }
        description="Development-only reference for shared OS components and responsive page contracts."
        eyebrow="Phase UX2"
        meta={<StatusBadge tone="success">Reference ready</StatusBadge>}
        title="Stonegate design system"
      />

      <SectionPanel description="Stable command treatments for normal, destructive, and icon-only actions." eyebrow="Controls" title="Actions">
        <div className={styles.demoSection}>
          <div className={styles.row}>
            <Button icon={<Plus size={16} />}>Primary action</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="quiet">Quiet action</Button>
            <Button variant="danger">Delete</Button>
            <Button loading>Saving</Button>
            <Button disabled>Disabled</Button>
            <IconButton label="Search records" variant="secondary"><Search size={17} /></IconButton>
            <IconButton label="More actions"><MoreHorizontal size={18} /></IconButton>
          </div>
          <div className={styles.row}>
            <SegmentedControl ariaLabel="Display density" items={[{ label: "Comfortable", value: "comfortable" }, { label: "Compact", value: "compact" }]} onChange={setDensity} value={density} />
            <Menu label="More actions">
              <button type="button">Assign owner</button>
              <button type="button">Archive record</button>
            </Menu>
            <Button onClick={() => setDialogOpen(true)} variant="secondary">Open dialog</Button>
            <Button onClick={() => setDrawerOpen(true)} variant="secondary">Open drawer</Button>
          </div>
        </div>
      </SectionPanel>

      <SectionPanel description="Visible labels, help, validation, selection, and predictable control heights." eyebrow="Input" title="Forms">
        <div className={styles.formDemo}>
          <FormField hint="Use the seller's preferred name." htmlFor="reference-name" label="Seller name">
            <TextInput id="reference-name" placeholder="Enter a name" />
          </FormField>
          <FormField htmlFor="reference-stage" label="Stage">
            <Select defaultValue="qualified" id="reference-stage">
              <option value="new">New lead</option>
              <option value="qualified">Qualified</option>
              <option value="appointment">Appointment set</option>
            </Select>
          </FormField>
          <FormField error="Enter a valid ten-digit number." htmlFor="reference-phone" label="Phone">
            <TextInput aria-describedby="reference-phone-error" aria-invalid="true" defaultValue="404" id="reference-phone" />
          </FormField>
          <FormField htmlFor="reference-owner" label="Owner" optional>
            <TextInput disabled id="reference-owner" value="Unassigned" readOnly />
          </FormField>
          <FormField htmlFor="reference-note" label="Internal note" optional>
            <TextArea id="reference-note" placeholder="Add context for the next person..." />
          </FormField>
          <div className={styles.checkboxDemo}>
            <Checkbox defaultChecked description="Notify the lead manager when this record changes." label="Follow this lead" />
          </div>
        </div>
      </SectionPanel>

      <SectionPanel description="Every state includes text and an icon so meaning never depends on color alone." eyebrow="Feedback" title="Status and system states">
        <div className={styles.demoSection}>
          <div className={styles.row}>
            <StatusBadge tone="success">Ready</StatusBadge>
            <StatusBadge tone="warning">Due soon</StatusBadge>
            <StatusBadge tone="danger">Blocked</StatusBadge>
            <StatusBadge tone="info">Needs review</StatusBadge>
            <StatusBadge>Draft</StatusBadge>
          </div>
          <div className={styles.alertGrid}>
            <Alert title="Changes saved" tone="success">The lead record and audit history were updated.</Alert>
            <Alert title="Approval required" tone="warning">A person must approve this offer before it can be shared.</Alert>
            <Alert title="Request failed" tone="danger">The record was not changed. Review the fields and try again.</Alert>
            <Alert title="Assignment changed">This conversation now belongs to the acquisitions team.</Alert>
          </div>
          {toastVisible ? <Toast message="Follow-up created for tomorrow at 9:00 AM." onDismiss={() => setToastVisible(false)} /> : <Button onClick={() => setToastVisible(true)} variant="secondary">Show toast</Button>}
        </div>
      </SectionPanel>

      <SectionPanel description="Tabs organize related record content; tables retain keyboard-accessible horizontal scrolling." eyebrow="Content" title="Navigation and data states">
        <div className={styles.demoSection}>
          <Tabs ariaLabel="Lead record sections" items={[{ label: "Summary", value: "summary" }, { count: 8, label: "Activity", value: "activity" }, { count: 3, label: "Documents", value: "documents" }]} onChange={setTab} value={tab} />
          <TableShell label="Example lead records">
            <table>
              <thead><tr><th>Seller</th><th>Stage</th><th>Owner</th><th>Next action</th></tr></thead>
              <tbody>
                <tr><td>Mary Johnson</td><td><StatusBadge tone="success">Qualified</StatusBadge></td><td>A. Rivera</td><td>Call today, 2:00 PM</td></tr>
                <tr><td>Robert Keller</td><td><StatusBadge tone="warning">Follow-up</StatusBadge></td><td>D. Stone</td><td>Review repair estimate</td></tr>
              </tbody>
            </table>
          </TableShell>
          <div className={styles.stateGrid}>
            <EmptyState action={<Button size="small" variant="secondary">Clear filters</Button>} icon={<Inbox size={20} />} message="No records match the current owner and due-date filters." title="No matching work" />
            <div aria-label="Loading example" className={styles.loadingState}>
              <Skeleton className={styles.skeletonTitle} />
              <Skeleton />
              <Skeleton />
              <Skeleton className={styles.skeletonShort} />
            </div>
          </div>
        </div>
      </SectionPanel>

      <RecordSummaryHeader
        actions={<><Button size="small" variant="secondary">Add note</Button><Button size="small">Open lead</Button></>}
        eyebrow="Qualified seller"
        facts={[{ label: "Owner", value: "A. Rivera" }, { label: "Stage", value: <StatusBadge tone="success">Appointment set</StatusBadge> }, { label: "Next action", value: "Today, 2:00 PM" }, { label: "Market", value: "Atlanta" }]}
        subtitle="1148 Madison Ave NE, Atlanta, GA 30306"
        title="Mary Johnson"
      />

      <SectionPanel actions={<SegmentedControl ariaLabel="Page contract" items={[{ label: "Queue", value: "queue" }, { label: "Record", value: "record" }, { label: "Pipeline", value: "pipeline" }, { label: "Calendar", value: "calendar" }, { label: "Management", value: "management" }]} onChange={setContract} value={contract} />} description="Responsive structures establish hierarchy without prescribing each workspace's business content." eyebrow="Layouts" title="Page contracts">
        <div className={styles.contractDemo}>
          {contract === "queue" ? (
            <QueuePageContract context={<Placeholder>Seller and property context</Placeholder>} detail={<Placeholder strong>Unified work timeline</Placeholder>} queue={<div className={styles.queueList}>{queueRows.map((row) => <button key={row} type="button">{row}<span>Needs reply</span></button>)}</div>} toolbar={<><Button icon={<SlidersHorizontal size={15} />} size="small" variant="secondary">Filters</Button><TextInput aria-label="Search queue" placeholder="Search work" /></>} />
          ) : null}
          {contract === "record" ? <RecordPageContract aside={<Placeholder>Tasks, notes, and context</Placeholder>} navigation={<Tabs ariaLabel="Record example" items={[{ label: "Summary", value: "summary" }, { label: "Activity", value: "activity" }, { label: "Documents", value: "documents" }]} onChange={setTab} value={tab} />}><Placeholder strong>Primary record content</Placeholder></RecordPageContract> : null}
          {contract === "pipeline" ? <PipelinePageContract toolbar={<Button icon={<SlidersHorizontal size={15} />} size="small" variant="secondary">Filters</Button>}>{["New", "Qualified", "Appointment", "Offer"].map((stage) => <div className={styles.pipelineColumn} key={stage}><strong>{stage}</strong><Placeholder>Opportunity cards</Placeholder></div>)}</PipelinePageContract> : null}
          {contract === "calendar" ? <CalendarPageContract calendar={<Placeholder strong>Week, day, month, or agenda calendar</Placeholder>} sidebar={<Placeholder>People, markets, and event filters</Placeholder>} toolbar={<Button icon={<CalendarDays size={15} />} size="small" variant="secondary">Today</Button>} /> : null}
          {contract === "management" ? <ManagementPageContract navigation={<div className={styles.managementNav}><button type="button">General</button><button type="button">Permissions</button><button type="button">Audit history</button></div>}><Placeholder strong>Focused configuration section</Placeholder></ManagementPageContract> : null}
        </div>
      </SectionPanel>

      <StickyActionBar actions={<><Button variant="quiet">Discard</Button><Button>Save changes</Button></>}><strong>Unsaved changes</strong><br />Review the record before leaving this page.</StickyActionBar>

      <Dialog description="A governed decision requires a clear consequence and explicit action." footer={<><Button onClick={() => setDialogOpen(false)} variant="quiet">Cancel</Button><Button onClick={() => setDialogOpen(false)}>Approve offer</Button></>} onClose={() => setDialogOpen(false)} open={dialogOpen} title="Approve seller offer"><Alert title="Offer within policy" tone="success">The offer is inside the approved range and has complete underwriting evidence.</Alert></Dialog>
      <Drawer description="Secondary context stays available without displacing the primary task." footer={<Button onClick={() => setDrawerOpen(false)}>Done</Button>} onClose={() => setDrawerOpen(false)} open={drawerOpen} title="Lead context"><div className={styles.drawerFacts}><strong>Mary Johnson</strong><span>Appointment set</span><span>Atlanta market</span><span>Follow-up today</span></div></Drawer>
    </WorkspacePage>
  );
}
