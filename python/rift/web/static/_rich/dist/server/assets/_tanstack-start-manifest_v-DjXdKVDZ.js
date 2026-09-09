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
			"/tuning"
		],
		preloads: [
			"/assets/index-DMQedyHc.js",
			"/assets/useRouter-Cox3-v4z.js",
			"/assets/link-CLCnZy0q.js",
			"/assets/useStore-EK8a_hkd.js",
			"/assets/Match-BbSpMIAa.js",
			"/assets/redirect-1Dss4sOM.js"
		],
		scripts: [{ attrs: {
			type: "module",
			async: !0,
			src: "/assets/index-DMQedyHc.js"
		} }]
	},
	"/": {
		filePath: "ui/src/routes/index.tsx",
		children: void 0,
		preloads: [
			"/assets/routes-D69zjnsi.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/arrow-right-CSbcfKV3.js",
			"/assets/plus-ioIJHPm1.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/deployments": {
		filePath: "ui/src/routes/deployments.tsx",
		children: ["/deployments/$id", "/deployments/"],
		preloads: ["/assets/deployments-BzAwbzDI.js"]
	},
	"/groups": {
		filePath: "ui/src/routes/groups.tsx",
		children: void 0,
		preloads: [
			"/assets/groups-CTsssyJK.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js"
		]
	},
	"/models": {
		filePath: "ui/src/routes/models.tsx",
		children: void 0,
		preloads: [
			"/assets/models-CWWvw3st.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/search-t7QbaGwF.js",
			"/assets/sparkles-DM0Xbk_s.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/nodes": {
		filePath: "ui/src/routes/nodes.tsx",
		children: ["/nodes/$id", "/nodes/"],
		preloads: ["/assets/nodes-BD8_6ghO.js"]
	},
	"/operations": {
		filePath: "ui/src/routes/operations.tsx",
		children: void 0,
		preloads: [
			"/assets/operations-DzhLza6J.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/settings": {
		filePath: "ui/src/routes/settings.tsx",
		children: void 0,
		preloads: [
			"/assets/settings-Dbfa0Y6u.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js"
		]
	},
	"/setup": {
		filePath: "ui/src/routes/setup.tsx",
		children: void 0,
		preloads: [
			"/assets/setup-DnkHbgjH.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/arrow-right-CSbcfKV3.js",
			"/assets/gauge-CqkQEB4q.js",
			"/assets/loader-circle-9wc2Urp3.js",
			"/assets/network-B-V9WDr-.js",
			"/assets/shield-check-Ckv5kZkX.js",
			"/assets/sparkles-DM0Xbk_s.js",
			"/assets/zap-bWmvO6J5.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/tuning": {
		filePath: "ui/src/routes/tuning.tsx",
		children: void 0,
		preloads: [
			"/assets/tuning-C9O5LtpP.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/loader-circle-9wc2Urp3.js",
			"/assets/shield-check-Ckv5kZkX.js",
			"/assets/zap-bWmvO6J5.js"
		]
	},
	"/deployments/$id": {
		filePath: "ui/src/routes/deployments.$id.tsx",
		children: void 0,
		preloads: [
			"/assets/deployments._id-CvcdVctm.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/gauge-CqkQEB4q.js",
			"/assets/loader-circle-9wc2Urp3.js",
			"/assets/rotate-ccw-D943C6zm.js",
			"/assets/shield-check-Ckv5kZkX.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/nodes/$id": {
		filePath: "ui/src/routes/nodes.$id.tsx",
		children: void 0,
		preloads: [
			"/assets/nodes._id-DUxeco0Y.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/format-C2MunlXt.js"
		]
	},
	"/deployments/": {
		filePath: "ui/src/routes/deployments.index.tsx",
		children: void 0,
		preloads: [
			"/assets/deployments.index-ChdxMFam.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/loader-circle-9wc2Urp3.js",
			"/assets/plus-ioIJHPm1.js",
			"/assets/rotate-ccw-D943C6zm.js",
			"/assets/search-t7QbaGwF.js"
		]
	},
	"/nodes/": {
		filePath: "ui/src/routes/nodes.index.tsx",
		children: void 0,
		preloads: [
			"/assets/nodes.index-CUF-85KV.js",
			"/assets/primitives-TQgpDgng.js",
			"/assets/unavailable-CWxVMCrv.js",
			"/assets/network-B-V9WDr-.js",
			"/assets/shield-check-Ckv5kZkX.js",
			"/assets/format-C2MunlXt.js"
		]
	}
} });
//#endregion
export { tsrStartManifest };
