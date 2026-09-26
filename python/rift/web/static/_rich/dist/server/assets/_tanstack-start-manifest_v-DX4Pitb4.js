//#region \0tanstack-start-manifest:v
var tsrStartManifest = () => ({ routes: {
	__root__: {
		filePath: "ui/src/routes/__root.tsx",
		children: [
			"/",
			"/deployments",
			"/groups",
			"/models",
			"/nodes",
			"/operations",
			"/overview",
			"/settings",
			"/setup",
			"/tuning",
			"/workloads"
		],
		preloads: [
			"/assets/index-L_gwrzQk.js",
			"/assets/useRouter-BJ5XiiId.js",
			"/assets/link-BzUDk2md.js",
			"/assets/useStore-CZ4Vj-0x.js",
			"/assets/Match-DAenvVbW.js",
			"/assets/redirect-1Dss4sOM.js",
			"/assets/QueryClientProvider-DoeuCcbw.js"
		],
		scripts: [{ attrs: {
			type: "module",
			async: !0,
			src: "/assets/index-L_gwrzQk.js"
		} }]
	},
	"/": {
		filePath: "ui/src/routes/index.tsx",
		children: void 0,
		preloads: ["/assets/routes-DJ7LAi8J.js"]
	},
	"/deployments": {
		filePath: "ui/src/routes/deployments.tsx",
		children: ["/deployments/$id", "/deployments/"],
		preloads: ["/assets/deployments-OxV8QOYk.js"]
	},
	"/groups": {
		filePath: "ui/src/routes/groups.tsx",
		children: void 0,
		preloads: [
			"/assets/groups-rVzpkZns.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/models": {
		filePath: "ui/src/routes/models.tsx",
		children: ["/models/catalog"],
		preloads: [
			"/assets/models-BlnTzWD9.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/refresh-cw-Bo3Rony5.js",
			"/assets/search-BV6q8ZeB.js",
			"/assets/sparkles-CjtPew0o.js",
			"/assets/format-C2MunlXt.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/nodes": {
		filePath: "ui/src/routes/nodes.tsx",
		children: ["/nodes/$id", "/nodes/"],
		preloads: ["/assets/nodes-Cbpk7XUs.js"]
	},
	"/operations": {
		filePath: "ui/src/routes/operations.tsx",
		children: void 0,
		preloads: [
			"/assets/operations-e9TF2C2Q.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/format-C2MunlXt.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/overview": {
		filePath: "ui/src/routes/overview.tsx",
		children: void 0,
		preloads: [
			"/assets/overview-CQtY6JHh.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/resource-history-BVwUYymZ.js",
			"/assets/arrow-right-VOOTJUGb.js",
			"/assets/live-state-N6RvRK-z.js",
			"/assets/plus-BYdVhCNu.js",
			"/assets/format-C2MunlXt.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/settings": {
		filePath: "ui/src/routes/settings.tsx",
		children: void 0,
		preloads: [
			"/assets/settings-qf2sM2AM.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/setup": {
		filePath: "ui/src/routes/setup.tsx",
		children: void 0,
		preloads: [
			"/assets/setup-BWhn0e9N.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/arrow-right-VOOTJUGb.js",
			"/assets/gauge-P2UD_Wkf.js",
			"/assets/loader-circle-BxEUfb0n.js",
			"/assets/network-BZ49_U82.js",
			"/assets/refresh-cw-Bo3Rony5.js",
			"/assets/shield-check-BDpkm1Bl.js",
			"/assets/sparkles-CjtPew0o.js",
			"/assets/triangle-alert-CPPFOS1K.js",
			"/assets/zap-Dy9-v5Il.js",
			"/assets/format-C2MunlXt.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/tuning": {
		filePath: "ui/src/routes/tuning.tsx",
		children: void 0,
		preloads: [
			"/assets/tuning-BQWUulDw.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/loader-circle-BxEUfb0n.js",
			"/assets/shield-check-BDpkm1Bl.js",
			"/assets/zap-Dy9-v5Il.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/workloads": {
		filePath: "ui/src/routes/workloads.tsx",
		children: void 0,
		preloads: [
			"/assets/workloads-DNnDoBbX.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js"
		]
	},
	"/deployments/$id": {
		filePath: "ui/src/routes/deployments.$id.tsx",
		children: void 0,
		preloads: [
			"/assets/deployments._id-B7tTzkPA.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/resource-history-BVwUYymZ.js",
			"/assets/gauge-P2UD_Wkf.js",
			"/assets/loader-circle-BxEUfb0n.js",
			"/assets/rotate-ccw-oSEs9Sci.js",
			"/assets/shield-check-BDpkm1Bl.js",
			"/assets/format-C2MunlXt.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/models/catalog": {
		filePath: "ui/src/routes/models.catalog.tsx",
		children: void 0,
		preloads: ["/assets/models.catalog-1PPE4R-h.js", "/assets/live-state-N6RvRK-z.js"]
	},
	"/nodes/$id": {
		filePath: "ui/src/routes/nodes.$id.tsx",
		children: void 0,
		preloads: [
			"/assets/nodes._id-DKbedN2y.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/format-C2MunlXt.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/deployments/": {
		filePath: "ui/src/routes/deployments.index.tsx",
		children: void 0,
		preloads: [
			"/assets/deployments.index-DtxblVgE.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/loader-circle-BxEUfb0n.js",
			"/assets/plus-BYdVhCNu.js",
			"/assets/rotate-ccw-oSEs9Sci.js",
			"/assets/search-BV6q8ZeB.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	},
	"/nodes/": {
		filePath: "ui/src/routes/nodes.index.tsx",
		children: void 0,
		preloads: [
			"/assets/nodes.index-CtmHMF_m.js",
			"/assets/primitives-BWKwJQp7.js",
			"/assets/hooks-Dn2CnhBF.js",
			"/assets/network-BZ49_U82.js",
			"/assets/shield-check-BDpkm1Bl.js",
			"/assets/format-C2MunlXt.js",
			"/assets/unavailable-DvbG16PZ.js"
		]
	}
} });
//#endregion
export { tsrStartManifest };
