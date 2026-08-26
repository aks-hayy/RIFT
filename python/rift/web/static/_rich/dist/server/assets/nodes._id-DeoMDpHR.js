import { i as createFileRoute, n as objectType, r as lazyRouteComponent, t as enumType } from "./types-hah6IYMp.js";
//#region src/routes/nodes.$id.tsx
var $$splitComponentImporter = () => import("./nodes._id-CVN8HUxj.js");
var searchSchema = objectType({ tab: enumType([
	"hardware",
	"assignments",
	"backends",
	"cache",
	"health",
	"diagnostics"
]).catch("hardware") });
var Route = createFileRoute("/nodes/$id")({
	validateSearch: searchSchema,
	head: ({ params }) => ({ meta: [{ title: `${params.id} — Node` }] }),
	component: lazyRouteComponent($$splitComponentImporter, "component")
});
//#endregion
export { Route as t };
