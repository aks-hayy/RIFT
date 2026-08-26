import { i as createFileRoute, n as objectType, r as lazyRouteComponent, t as enumType } from "./types-hah6IYMp.js";
//#region src/routes/operations.tsx
var $$splitComponentImporter = () => import("./operations-xIN_mX3g.js");
var searchSchema = objectType({ tab: enumType([
	"incidents",
	"rollouts",
	"audit",
	"logs",
	"metrics"
]).catch("incidents") });
var Route = createFileRoute("/operations")({
	validateSearch: searchSchema,
	head: () => ({ meta: [
		{ title: "Operations — RIFT" },
		{
			name: "description",
			content: "Incidents, rollouts, audit log, fleet logs, and metrics."
		},
		{
			property: "og:title",
			content: "Operations — RIFT"
		},
		{
			property: "og:description",
			content: "Incidents, rollouts, audit log, fleet logs, and metrics."
		}
	] }),
	component: lazyRouteComponent($$splitComponentImporter, "component")
});
//#endregion
export { Route as t };
