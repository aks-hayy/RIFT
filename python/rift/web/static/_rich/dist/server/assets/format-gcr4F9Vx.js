//#region src/lib/rift/format.ts
function bytes(n) {
	if (!n && n !== 0) return "—";
	const units = [
		"B",
		"KB",
		"MB",
		"GB",
		"TB"
	];
	let i = 0;
	let v = n;
	while (v >= 1024 && i < units.length - 1) {
		v /= 1024;
		i++;
	}
	return `${v.toFixed(v >= 100 || i === 0 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`;
}
function relativeTime(iso) {
	if (!iso) return "—";
	const t = new Date(iso).getTime();
	const diff = Date.now() - t;
	if (diff < 6e4) return "just now";
	if (diff < 36e5) return `${Math.round(diff / 6e4)}m ago`;
	if (diff < 864e5) return `${Math.round(diff / 36e5)}h ago`;
	return `${Math.round(diff / 864e5)}d ago`;
}
function pct(used, total) {
	if (!total) return 0;
	return Math.max(0, Math.min(100, used / total * 100));
}
//#endregion
export { pct as n, relativeTime as r, bytes as t };
