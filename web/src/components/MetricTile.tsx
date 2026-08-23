interface MetricTileProps {
  label: string;
  value: number | string;
}

export default function MetricTile({ label, value }: MetricTileProps) {
  return (
    <div className="metric-tile">
      <div className="metric-tile__value">{value}</div>
      <div className="metric-tile__label">{label}</div>
    </div>
  );
}
