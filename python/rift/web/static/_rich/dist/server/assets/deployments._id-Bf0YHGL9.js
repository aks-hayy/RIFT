import { i as createFileRoute, n as objectType, r as lazyRouteComponent, t as enumType } from "./types-CPlfyJGB.js";
//#region src/routes/deployments.$id.tsx
var $$splitComponentImporter = () => import("./deployments._id-D6IcgM_M.js");
var searchSchema = objectType({ tab: enumType([
	"overview",
	"playground",
	"benchmarking",
	"performance",
	"monitoring",
	"tuning",
	"logs",
	"configuration",
	"revisions"
]).catch("overview") });
var Route = createFileRoute("/deployments/$id")({
	validateSearch: searchSchema,
	head: ({ params }) => ({ meta: [{ title: `${params.id} — Deployment` }, {
		name: "description",
		content: `Deployment detail for ${params.id}.`
	}] }),
	component: lazyRouteComponent($$splitComponentImporter, "component")
});
//#endregion
export { Route as t };
