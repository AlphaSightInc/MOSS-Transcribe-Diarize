/**
 * #8: a desktop side panel folds into a 48 px rail (reference LiveTranscribe). The chevron sits in the
 * panel head; the collapsed rail shows the chevron and the panel name written vertically, and either
 * one opens the panel again. Layout lives in styles/index.css; below desktop width both are hidden.
 */
export function PanelCollapseButton({ name, side, collapsed, onChange }: {
  name: string;
  side: "left" | "right";
  collapsed: boolean;
  onChange: (collapsed: boolean) => void;
}) {
  const label = `${collapsed ? "Expand" : "Collapse"} ${name.toLowerCase()}`;
  // The chevron points where the panel edge will move: outward to collapse, inward to expand.
  const pointsLeft = (side === "left") !== collapsed;
  return (
    <button type="button" className="collapse-btn" aria-label={label} title={label}
      onClick={() => onChange(!collapsed)}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
        strokeLinejoin="round" aria-hidden="true">
        <polyline points={pointsLeft ? "15 18 9 12 15 6" : "9 18 15 12 9 6"} />
      </svg>
    </button>
  );
}

/** The vertical panel name on a collapsed rail; hidden while the panel is open. */
export function PanelRailTitle({ name, onExpand }: { name: string; onExpand: () => void }) {
  return <button type="button" className="panel-title-rail" tabIndex={-1} onClick={onExpand}>{name}</button>;
}
