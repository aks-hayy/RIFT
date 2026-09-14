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
			"/settings",
			"/setup",
			"/tuning",
			"/workloads"
		],
		preloads: [
			"/assets/index-BsjWb-7S.js",
			"/assets/useRouter-BJ5XiiId.js",
			"/assets/link-BzUDk2md.js",
			"/assets/useStore-CZ4Vj-0x.js",
			"/assets/Match-DAenvVbW.js",
			"/assets/redirect-1Dss4sOM.js",
			"/assets/QueryClientProvider-CIAPw9yt.js"
		],
		scripts: [{ attrs: {
			type: "module",
			async: !0,
			src: "/assets/index-BsjWb-7S.js"
		} }]
	},
	"/": {
		filePath: "ui/src/routes/index.tsx",
		children: void 0,
		preloads: [
			"/assets/routes-GDDJqTcd.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/arrow-right-C-J6_7Wb.js",
			"/assets/plus-BwRf5LRh.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/format-C2MunlXt.js",
			"/assets/resource-history-DRC9TqgZ.js"
		]
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
			"/assets/groups-ErcDbqr_.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/unavailable-BMlUhNVm.js"
		]
	},
	"/models": {
		filePath: "ui/src/routes/models.tsx",
		children: void 0,
		preloads: [
			"/assets/models-C_JB1sP3.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/search-DFPKgz3P.js",
			"/assets/sparkles-DWfg6tpi.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/format-C2MunlXt.js"
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
			"/assets/operations-BMxtVH_v.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/settings": {
		filePath: "ui/src/routes/settings.tsx",
		children: void 0,
		preloads: [
			"/assets/settings-C-fbbwHO.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/unavailable-BMlUhNVm.js"
		]
	},
	"/setup": {
		filePath: "ui/src/routes/setup.tsx",
		children: void 0,
		preloads: [
			"/assets/setup-Di-VyfQt.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/arrow-right-C-J6_7Wb.js",
			"/assets/gauge-BDOgRZDV.js",
			"/assets/loader-circle-8YrCZUs1.js",
			"/assets/network-DHrf2zNW.js",
			"/assets/shield-check-C9spr9oE.js",
			"/assets/sparkles-DWfg6tpi.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/zap-D4xqc9i9.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/tuning": {
		filePath: "ui/src/routes/tuning.tsx",
		children: void 0,
		preloads: [
			"/assets/tuning-ZQDzoyC2.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/loader-circle-8YrCZUs1.js",
			"/assets/shield-check-C9spr9oE.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/zap-D4xqc9i9.js"
		]
	},
	"/workloads": {
		filePath: "ui/src/routes/workloads.tsx",
		children: void 0,
		preloads: [
			"/assets/workloads-CnnJIUiY.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js"
		]
	},
	"/deployments/$id": {
		filePath: "ui/src/routes/deployments.$id.tsx",
		children: void 0,
		preloads: [
			"/assets/deployments._id-D6whVjUE.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/gauge-BDOgRZDV.js",
			"/assets/loader-circle-8YrCZUs1.js",
			"/assets/rotate-ccw-BxusugGC.js",
			"/assets/shield-check-C9spr9oE.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/format-C2MunlXt.js",
			"/assets/resource-history-DRC9TqgZ.js"
		]
	},
	"/nodes/$id": {
		filePath: "ui/src/routes/nodes.$id.tsx",
		children: void 0,
		preloads: [
			"/assets/nodes._id-DpPNzRMx.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/deployments/": {
		filePath: "ui/src/routes/deployments.index.tsx",
		children: void 0,
		preloads: [
			"/assets/deployments.index-CCJiFBC7.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/loader-circle-8YrCZUs1.js",
			"/assets/plus-BwRf5LRh.js",
			"/assets/rotate-ccw-BxusugGC.js",
			"/assets/search-DFPKgz3P.js",
			"/assets/unavailable-BMlUhNVm.js"
		]
	},
	"/nodes/": {
		filePath: "ui/src/routes/nodes.index.tsx",
		children: void 0,
		preloads: [
			"/assets/nodes.index-Bh7GtIp5.js",
			"/assets/primitives-Dh8QSW-p.js",
			"/assets/hooks-BbQCQ-pf.js",
			"/assets/network-DHrf2zNW.js",
			"/assets/shield-check-C9spr9oE.js",
			"/assets/unavailable-BMlUhNVm.js",
			"/assets/format-C2MunlXt.js"
		]
	}
} });
//#endregion
export { tsrStartManifest };
