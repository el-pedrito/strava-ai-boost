import { useTheme } from '@/theme/ThemeProvider';

export interface ChartTheme {
  axisColor: string;
  gridColor: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  primaryColor: string;
  successColor: string;
  mutedColor: string;
}

export function useChartTheme(): ChartTheme {
  const { theme } = useTheme();
  if (theme === 'dark') {
    return {
      axisColor: '#94a3b8',
      gridColor: '#1f2937',
      tooltipBg: 'rgba(17, 24, 39, 0.95)',
      tooltipBorder: '#334155',
      tooltipText: '#f5f7fa',
      primaryColor: '#FC4C02',
      successColor: '#00c896',
      mutedColor: '#64748b',
    };
  }
  return {
    axisColor: '#64748b',
    gridColor: '#e5e7eb',
    tooltipBg: 'rgba(255, 255, 255, 0.95)',
    tooltipBorder: '#cbd5e1',
    tooltipText: '#0f172a',
    primaryColor: '#FC4C02',
    successColor: '#00a87d',
    mutedColor: '#94a3b8',
  };
}

interface TooltipPayloadEntry {
  name?: string;
  value?: number | string;
  color?: string;
  dataKey?: string | number;
  payload?: Record<string, unknown>;
}

export interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string | number;
  valueFormatter?: (value: number | string, name?: string) => string;
  labelFormatter?: (label: string | number) => string;
  subtextFormatter?: (
    payload: TooltipPayloadEntry[],
    label: string | number | undefined,
  ) => string | null;
}

export function ChartTooltip({
  active,
  payload,
  label,
  valueFormatter,
  labelFormatter,
  subtextFormatter,
}: ChartTooltipProps) {
  const theme = useChartTheme();
  if (!active || !payload || payload.length === 0) return null;

  const formattedLabel =
    labelFormatter && label !== undefined ? labelFormatter(label) : label;
  const subtext = subtextFormatter ? subtextFormatter(payload, label) : null;

  return (
    <div
      className="rounded-lg border px-3 py-2 shadow-lg backdrop-blur-md text-xs"
      style={{
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        color: theme.tooltipText,
      }}
    >
      {formattedLabel !== undefined && formattedLabel !== '' ? (
        <div
          className="font-medium mb-1"
          style={{ color: theme.tooltipText }}
        >
          {formattedLabel}
        </div>
      ) : null}
      <div className="flex flex-col gap-0.5">
        {payload.map((entry, idx) => {
          const value = entry.value;
          const formatted =
            valueFormatter && value !== undefined
              ? valueFormatter(value, entry.name)
              : String(value);
          return (
            <div key={idx} className="flex items-center gap-2">
              {entry.color ? (
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: entry.color }}
                  aria-hidden="true"
                />
              ) : null}
              {entry.name ? (
                <span style={{ color: theme.mutedColor }}>{entry.name}:</span>
              ) : null}
              <span className="font-numeric font-medium">{formatted}</span>
            </div>
          );
        })}
      </div>
      {subtext ? (
        <div
          className="mt-1 pt-1 border-t text-[11px] leading-tight"
          style={{ borderColor: theme.tooltipBorder, color: theme.mutedColor }}
        >
          {subtext}
        </div>
      ) : null}
    </div>
  );
}
