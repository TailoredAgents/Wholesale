import styles from "./record-timeline.module.css";

export type RecordTimelineItem = {
  description?: string | null;
  id: string;
  meta: string;
  title: string;
};

export function RecordTimeline({
  emptyLabel = "No activity recorded.",
  items,
}: {
  emptyLabel?: string;
  items: RecordTimelineItem[];
}) {
  if (!items.length) return <p className={styles.empty}>{emptyLabel}</p>;

  return (
    <div className={styles.timeline}>
      {items.map((item) => (
        <article key={item.id}>
          <span aria-hidden="true" />
          <div>
            <strong>{item.title}</strong>
            {item.description ? <p>{item.description}</p> : null}
            <small>{item.meta}</small>
          </div>
        </article>
      ))}
    </div>
  );
}
