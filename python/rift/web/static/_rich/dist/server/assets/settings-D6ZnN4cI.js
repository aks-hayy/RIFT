import { i as createFileRoute, n as objectType, r as lazyRouteComponent, t as enumType } from "./types-hah6IYMp.js";
//#region src/routes/settings.tsx
var $$splitComponentImporter = () => import("./settings-Dd4Ckbth.js");
var searchSchema = objectType({ tab: enumType([
	"controller",
	"sources",
	"security",
	"policies",
	"users",
	"integrations"
]).catch("controller") });
var Route = createFileRoute("/settings")({
	validateSearch: searchSchema,
	head: () => ({ meta: [
		{ title: "Settings — RIFT" },
		{
			name: "description",
			content: "Controller, sources, security, policies, users, integrations."
		},
		{
			property: "og:title",
			content: "Settings — RIFT"
		},
		{
			property: "og:description",
			content: "Controller, sources, security, policies, users, integrations."
		}
	] }),
	component: lazyRouteComponent($$splitComponentImporter, "component")
});
//#endregion
export { Route as t };
