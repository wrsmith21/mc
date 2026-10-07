export default function StatusChip({ status, label }: { status: string; label: string }) {
  return <span className={`chip ${status}`}>{label}</span>
}
