"use client";

import {
  AlertCircle,
  Ban,
  Check,
  CheckCircle2,
  Clock3,
  Info,
  LoaderCircle,
  X,
} from "lucide-react";
import {
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useEffect,
  useId,
  useRef,
} from "react";

import styles from "./design-system.module.css";

function classes(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";
type ButtonSize = "small" | "medium" | "large";

export function Button({
  children,
  className,
  icon,
  loading = false,
  size = "medium",
  variant = "primary",
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: ReactNode;
  loading?: boolean;
  size?: ButtonSize;
  variant?: ButtonVariant;
}) {
  return (
    <button
      className={classes(styles.button, styles[variant], styles[size], className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <LoaderCircle aria-hidden="true" className={styles.spinner} size={16} /> : icon}
      <span>{children}</span>
    </button>
  );
}

export function IconButton({
  label,
  className,
  variant = "quiet",
  size = "medium",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
}) {
  return (
    <button
      aria-label={label}
      className={classes(styles.iconButton, styles[variant], styles[size], className)}
      data-tooltip={label}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}

export function FormField({
  children,
  error,
  hint,
  htmlFor,
  label,
  optional = false,
}: {
  children: ReactNode;
  error?: string;
  hint?: string;
  htmlFor: string;
  label: string;
  optional?: boolean;
}) {
  return (
    <div className={styles.formField}>
      <label htmlFor={htmlFor}>
        {label}
        {optional ? <span>Optional</span> : null}
      </label>
      {children}
      {error ? (
        <p className={styles.fieldError} id={`${htmlFor}-error`}>
          <AlertCircle aria-hidden="true" size={14} />
          {error}
        </p>
      ) : hint ? (
        <p className={styles.fieldHint} id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={classes(styles.control, className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={classes(styles.control, className)} {...props}>
      {children}
    </select>
  );
}

export function TextArea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={classes(styles.control, styles.textArea, className)} {...props} />;
}

export function Checkbox({
  label,
  description,
  id: suppliedId,
  className,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string;
  description?: string;
}) {
  const generatedId = useId();
  const id = suppliedId ?? generatedId;
  return (
    <label className={classes(styles.checkbox, className)} htmlFor={id}>
      <input id={id} type="checkbox" {...props} />
      <span aria-hidden="true" className={styles.checkboxMark}>
        <Check size={14} />
      </span>
      <span className={styles.checkboxCopy}>
        <strong>{label}</strong>
        {description ? <small>{description}</small> : null}
      </span>
    </label>
  );
}

export function SegmentedControl<T extends string>({
  ariaLabel,
  items,
  onChange,
  value,
}: {
  ariaLabel: string;
  items: Array<{ label: string; value: T }>;
  onChange: (value: T) => void;
  value: T;
}) {
  return (
    <div aria-label={ariaLabel} className={styles.segmented} role="group">
      {items.map((item) => (
        <button
          aria-pressed={item.value === value}
          className={item.value === value ? styles.segmentActive : undefined}
          key={item.value}
          onClick={() => onChange(item.value)}
          type="button"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({
  ariaLabel,
  items,
  onChange,
  value,
}: {
  ariaLabel: string;
  items: Array<{ count?: number; label: string; value: T }>;
  onChange: (value: T) => void;
  value: T;
}) {
  return (
    <div aria-label={ariaLabel} className={styles.tabs} role="tablist">
      {items.map((item) => (
        <button
          aria-selected={item.value === value}
          className={item.value === value ? styles.tabActive : undefined}
          key={item.value}
          onClick={() => onChange(item.value)}
          role="tab"
          type="button"
        >
          {item.label}
          {item.count !== undefined ? <span>{item.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

const statusIcons: Record<StatusTone, ReactNode> = {
  success: <CheckCircle2 aria-hidden="true" size={14} />,
  warning: <Clock3 aria-hidden="true" size={14} />,
  danger: <Ban aria-hidden="true" size={14} />,
  info: <Info aria-hidden="true" size={14} />,
  neutral: <Clock3 aria-hidden="true" size={14} />,
};

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: StatusTone;
}) {
  return (
    <span className={classes(styles.badge, styles[`badge-${tone}`])}>
      {statusIcons[tone]}
      {children}
    </span>
  );
}

export function Alert({
  children,
  title,
  tone = "info",
}: {
  children: ReactNode;
  title: string;
  tone?: Exclude<StatusTone, "neutral">;
}) {
  return (
    <div className={classes(styles.alert, styles[`alert-${tone}`])} role="status">
      {tone === "success" ? <CheckCircle2 aria-hidden="true" /> : <AlertCircle aria-hidden="true" />}
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

export function EmptyState({
  action,
  icon,
  message,
  title,
}: {
  action?: ReactNode;
  icon?: ReactNode;
  message: string;
  title: string;
}) {
  return (
    <div className={styles.emptyState}>
      {icon ? <span className={styles.emptyIcon}>{icon}</span> : null}
      <strong>{title}</strong>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={classes(styles.skeleton, className)} {...props} />;
}

export function TableShell({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div aria-label={label} className={styles.tableShell} role="region" tabIndex={0}>
      {children}
    </div>
  );
}

export function Menu({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className={styles.menu}>
      <summary>{label}</summary>
      <div className={styles.menuItems}>{children}</div>
    </details>
  );
}

function OverlayDialog({
  children,
  description,
  footer,
  onClose,
  open,
  title,
  variant,
}: {
  children: ReactNode;
  description?: string;
  footer?: ReactNode;
  onClose: () => void;
  open: boolean;
  title: string;
  variant: "dialog" | "drawer";
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog
      aria-describedby={description ? descriptionId : undefined}
      aria-labelledby={titleId}
      className={classes(styles.overlay, styles[variant])}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
      ref={ref}
    >
      <div className={styles.overlayHeader}>
        <div>
          <h2 id={titleId}>{title}</h2>
          {description ? <p id={descriptionId}>{description}</p> : null}
        </div>
        <IconButton label="Close" onClick={onClose}>
          <X size={18} />
        </IconButton>
      </div>
      <div className={styles.overlayBody}>{children}</div>
      {footer ? <div className={styles.overlayFooter}>{footer}</div> : null}
    </dialog>
  );
}

export function Dialog(props: Omit<Parameters<typeof OverlayDialog>[0], "variant">) {
  return <OverlayDialog {...props} variant="dialog" />;
}

export function Drawer(props: Omit<Parameters<typeof OverlayDialog>[0], "variant">) {
  return <OverlayDialog {...props} variant="drawer" />;
}

export function Toast({
  message,
  onDismiss,
  tone = "success",
}: {
  message: string;
  onDismiss?: () => void;
  tone?: "success" | "danger" | "info";
}) {
  return (
    <output className={classes(styles.toast, styles[`toast-${tone}`])}>
      {tone === "success" ? <CheckCircle2 aria-hidden="true" size={18} /> : <Info aria-hidden="true" size={18} />}
      <span>{message}</span>
      {onDismiss ? (
        <IconButton label="Dismiss notification" onClick={onDismiss}>
          <X size={16} />
        </IconButton>
      ) : null}
    </output>
  );
}
