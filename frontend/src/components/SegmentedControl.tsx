interface SegmentedControlOption<Value extends string> {
  label: string;
  value: Value;
}

interface SegmentedControlProps<Value extends string> {
  ariaLabel: string;
  className?: string;
  disabled?: boolean;
  onChange: (value: Value) => void;
  options: readonly SegmentedControlOption<Value>[];
  value: Value;
}

// Ported unchanged from the reference control except for unused disabled support.
export function SegmentedControl<Value extends string>({
  ariaLabel,
  className,
  disabled = false,
  onChange,
  options,
  value
}: SegmentedControlProps<Value>) {
  return (
    <div className={["seg", className].filter(Boolean).join(" ")} role="tablist" aria-label={ariaLabel}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            className={`seg-btn${selected ? " is-active" : ""}`}
            role="tab"
            aria-selected={selected}
            disabled={disabled}
            onClick={() => {
              if (!disabled && !selected) {
                onChange(option.value);
              }
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
