import { i as require_react, r as require_jsx_runtime, s as __toESM } from "./useRouter-C_cgokP9.js";
//#region node_modules/lucide-react/dist/esm/shared/src/utils/mergeClasses.js
var import_react = /* @__PURE__ */ __toESM(require_react());
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var mergeClasses = (...classes) => classes.filter((className, index, array) => {
	return Boolean(className) && className.trim() !== "" && array.indexOf(className) === index;
}).join(" ").trim();
//#endregion
//#region node_modules/lucide-react/dist/esm/shared/src/utils/toKebabCase.js
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var toKebabCase = (string) => string.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
//#endregion
//#region node_modules/lucide-react/dist/esm/shared/src/utils/toCamelCase.js
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var toCamelCase = (string) => string.replace(/^([A-Z])|[\s-_]+(\w)/g, (match, p1, p2) => p2 ? p2.toUpperCase() : p1.toLowerCase());
//#endregion
//#region node_modules/lucide-react/dist/esm/shared/src/utils/toPascalCase.js
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var toPascalCase = (string) => {
	const camelCase = toCamelCase(string);
	return camelCase.charAt(0).toUpperCase() + camelCase.slice(1);
};
//#endregion
//#region node_modules/lucide-react/dist/esm/defaultAttributes.js
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var defaultAttributes = {
	xmlns: "http://www.w3.org/2000/svg",
	width: 24,
	height: 24,
	viewBox: "0 0 24 24",
	fill: "none",
	stroke: "currentColor",
	strokeWidth: 2,
	strokeLinecap: "round",
	strokeLinejoin: "round"
};
//#endregion
//#region node_modules/lucide-react/dist/esm/shared/src/utils/hasA11yProp.js
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var hasA11yProp = (props) => {
	for (const prop in props) if (prop.startsWith("aria-") || prop === "role" || prop === "title") return true;
	return false;
};
//#endregion
//#region node_modules/lucide-react/dist/esm/Icon.js
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Icon = (0, import_react.forwardRef)(({ color = "currentColor", size = 24, strokeWidth = 2, absoluteStrokeWidth, className = "", children, iconNode, ...rest }, ref) => (0, import_react.createElement)("svg", {
	ref,
	...defaultAttributes,
	width: size,
	height: size,
	stroke: color,
	strokeWidth: absoluteStrokeWidth ? Number(strokeWidth) * 24 / Number(size) : strokeWidth,
	className: mergeClasses("lucide", className),
	...!children && !hasA11yProp(rest) && { "aria-hidden": "true" },
	...rest
}, [...iconNode.map(([tag, attrs]) => (0, import_react.createElement)(tag, attrs)), ...Array.isArray(children) ? children : [children]]));
//#endregion
//#region node_modules/lucide-react/dist/esm/createLucideIcon.js
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var createLucideIcon = (iconName, iconNode) => {
	const Component = (0, import_react.forwardRef)(({ className, ...props }, ref) => (0, import_react.createElement)(Icon, {
		ref,
		iconNode,
		className: mergeClasses(`lucide-${toKebabCase(toPascalCase(iconName))}`, `lucide-${iconName}`, className),
		...props
	}));
	Component.displayName = toPascalCase(iconName);
	return Component;
};
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Terminal = createLucideIcon("terminal", [["path", {
	d: "M12 19h8",
	key: "baeox8"
}], ["path", {
	d: "m4 17 6-6-6-6",
	key: "1yngyt"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var TriangleAlert = createLucideIcon("triangle-alert", [
	["path", {
		d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
		key: "wmoenq"
	}],
	["path", {
		d: "M12 9v4",
		key: "juzpu7"
	}],
	["path", {
		d: "M12 17h.01",
		key: "p32p05"
	}]
]);
//#endregion
//#region node_modules/clsx/dist/clsx.mjs
function r(e) {
	var t, f, n = "";
	if ("string" == typeof e || "number" == typeof e) n += e;
	else if ("object" == typeof e) if (Array.isArray(e)) {
		var o = e.length;
		for (t = 0; t < o; t++) e[t] && (f = r(e[t])) && (n && (n += " "), n += f);
	} else for (f in e) e[f] && (n && (n += " "), n += f);
	return n;
}
function clsx() {
	for (var e, t, f = 0, n = "", o = arguments.length; f < o; f++) (e = arguments[f]) && (t = r(e)) && (n && (n += " "), n += t);
	return n;
}
//#endregion
//#region node_modules/tailwind-merge/dist/bundle-mjs.mjs
/**
* Concatenates two arrays faster than the array spread operator.
*/
var concatArrays = (array1, array2) => {
	const combinedArray = new Array(array1.length + array2.length);
	for (let i = 0; i < array1.length; i++) combinedArray[i] = array1[i];
	for (let i = 0; i < array2.length; i++) combinedArray[array1.length + i] = array2[i];
	return combinedArray;
};
var createClassValidatorObject = (classGroupId, validator) => ({
	classGroupId,
	validator
});
var createClassPartObject = (nextPart = /* @__PURE__ */ new Map(), validators = null, classGroupId) => ({
	nextPart,
	validators,
	classGroupId
});
var CLASS_PART_SEPARATOR = "-";
var EMPTY_CONFLICTS = [];
var ARBITRARY_PROPERTY_PREFIX = "arbitrary..";
var createClassGroupUtils = (config) => {
	const classMap = createClassMap(config);
	const { conflictingClassGroups, conflictingClassGroupModifiers } = config;
	const getClassGroupId = (className) => {
		if (className.startsWith("[") && className.endsWith("]")) return getGroupIdForArbitraryProperty(className);
		const classParts = className.split(CLASS_PART_SEPARATOR);
		return getGroupRecursive(classParts, classParts[0] === "" && classParts.length > 1 ? 1 : 0, classMap);
	};
	const getConflictingClassGroupIds = (classGroupId, hasPostfixModifier) => {
		if (hasPostfixModifier) {
			const modifierConflicts = conflictingClassGroupModifiers[classGroupId];
			const baseConflicts = conflictingClassGroups[classGroupId];
			if (modifierConflicts) {
				if (baseConflicts) return concatArrays(baseConflicts, modifierConflicts);
				return modifierConflicts;
			}
			return baseConflicts || EMPTY_CONFLICTS;
		}
		return conflictingClassGroups[classGroupId] || EMPTY_CONFLICTS;
	};
	return {
		getClassGroupId,
		getConflictingClassGroupIds
	};
};
var getGroupRecursive = (classParts, startIndex, classPartObject) => {
	if (classParts.length - startIndex === 0) return classPartObject.classGroupId;
	const currentClassPart = classParts[startIndex];
	const nextClassPartObject = classPartObject.nextPart.get(currentClassPart);
	if (nextClassPartObject) {
		const result = getGroupRecursive(classParts, startIndex + 1, nextClassPartObject);
		if (result) return result;
	}
	const validators = classPartObject.validators;
	if (validators === null) return;
	const classRest = startIndex === 0 ? classParts.join(CLASS_PART_SEPARATOR) : classParts.slice(startIndex).join(CLASS_PART_SEPARATOR);
	const validatorsLength = validators.length;
	for (let i = 0; i < validatorsLength; i++) {
		const validatorObj = validators[i];
		if (validatorObj.validator(classRest)) return validatorObj.classGroupId;
	}
};
/**
* Get the class group ID for an arbitrary property.
*
* @param className - The class name to get the group ID for. Is expected to be string starting with `[` and ending with `]`.
*/
var getGroupIdForArbitraryProperty = (className) => className.slice(1, -1).indexOf(":") === -1 ? void 0 : (() => {
	const content = className.slice(1, -1);
	const colonIndex = content.indexOf(":");
	const property = content.slice(0, colonIndex);
	return property ? ARBITRARY_PROPERTY_PREFIX + property : void 0;
})();
/**
* Exported for testing only
*/
var createClassMap = (config) => {
	const { theme, classGroups } = config;
	return processClassGroups(classGroups, theme);
};
var processClassGroups = (classGroups, theme) => {
	const classMap = createClassPartObject();
	for (const classGroupId in classGroups) {
		const group = classGroups[classGroupId];
		processClassesRecursively(group, classMap, classGroupId, theme);
	}
	return classMap;
};
var processClassesRecursively = (classGroup, classPartObject, classGroupId, theme) => {
	const len = classGroup.length;
	for (let i = 0; i < len; i++) {
		const classDefinition = classGroup[i];
		processClassDefinition(classDefinition, classPartObject, classGroupId, theme);
	}
};
var processClassDefinition = (classDefinition, classPartObject, classGroupId, theme) => {
	if (typeof classDefinition === "string") {
		processStringDefinition(classDefinition, classPartObject, classGroupId);
		return;
	}
	if (typeof classDefinition === "function") {
		processFunctionDefinition(classDefinition, classPartObject, classGroupId, theme);
		return;
	}
	processObjectDefinition(classDefinition, classPartObject, classGroupId, theme);
};
var processStringDefinition = (classDefinition, classPartObject, classGroupId) => {
	const classPartObjectToEdit = classDefinition === "" ? classPartObject : getPart(classPartObject, classDefinition);
	classPartObjectToEdit.classGroupId = classGroupId;
};
var processFunctionDefinition = (classDefinition, classPartObject, classGroupId, theme) => {
	if (isThemeGetter(classDefinition)) {
		processClassesRecursively(classDefinition(theme), classPartObject, classGroupId, theme);
		return;
	}
	if (classPartObject.validators === null) classPartObject.validators = [];
	classPartObject.validators.push(createClassValidatorObject(classGroupId, classDefinition));
};
var processObjectDefinition = (classDefinition, classPartObject, classGroupId, theme) => {
	const entries = Object.entries(classDefinition);
	const len = entries.length;
	for (let i = 0; i < len; i++) {
		const [key, value] = entries[i];
		processClassesRecursively(value, getPart(classPartObject, key), classGroupId, theme);
	}
};
var getPart = (classPartObject, path) => {
	let current = classPartObject;
	const parts = path.split(CLASS_PART_SEPARATOR);
	const len = parts.length;
	for (let i = 0; i < len; i++) {
		const part = parts[i];
		let next = current.nextPart.get(part);
		if (!next) {
			next = createClassPartObject();
			current.nextPart.set(part, next);
		}
		current = next;
	}
	return current;
};
var isThemeGetter = (func) => "isThemeGetter" in func && func.isThemeGetter === true;
var createLruCache = (maxCacheSize) => {
	if (maxCacheSize < 1) return {
		get: () => void 0,
		set: () => {}
	};
	let cacheSize = 0;
	let cache = Object.create(null);
	let previousCache = Object.create(null);
	const update = (key, value) => {
		cache[key] = value;
		cacheSize++;
		if (cacheSize > maxCacheSize) {
			cacheSize = 0;
			previousCache = cache;
			cache = Object.create(null);
		}
	};
	return {
		get(key) {
			let value = cache[key];
			if (value !== void 0) return value;
			if ((value = previousCache[key]) !== void 0) {
				update(key, value);
				return value;
			}
		},
		set(key, value) {
			if (key in cache) cache[key] = value;
			else update(key, value);
		}
	};
};
var IMPORTANT_MODIFIER = "!";
var MODIFIER_SEPARATOR = ":";
var EMPTY_MODIFIERS = [];
var createResultObject = (modifiers, hasImportantModifier, baseClassName, maybePostfixModifierPosition, isExternal) => ({
	modifiers,
	hasImportantModifier,
	baseClassName,
	maybePostfixModifierPosition,
	isExternal
});
var createParseClassName = (config) => {
	const { prefix, experimentalParseClassName } = config;
	/**
	* Parse class name into parts.
	*
	* Inspired by `splitAtTopLevelOnly` used in Tailwind CSS
	* @see https://github.com/tailwindlabs/tailwindcss/blob/v3.2.2/src/util/splitAtTopLevelOnly.js
	*/
	let parseClassName = (className) => {
		const modifiers = [];
		let bracketDepth = 0;
		let parenDepth = 0;
		let modifierStart = 0;
		let postfixModifierPosition;
		const len = className.length;
		for (let index = 0; index < len; index++) {
			const currentCharacter = className[index];
			if (bracketDepth === 0 && parenDepth === 0) {
				if (currentCharacter === MODIFIER_SEPARATOR) {
					modifiers.push(className.slice(modifierStart, index));
					modifierStart = index + 1;
					continue;
				}
				if (currentCharacter === "/") {
					postfixModifierPosition = index;
					continue;
				}
			}
			if (currentCharacter === "[") bracketDepth++;
			else if (currentCharacter === "]") bracketDepth--;
			else if (currentCharacter === "(") parenDepth++;
			else if (currentCharacter === ")") parenDepth--;
		}
		const baseClassNameWithImportantModifier = modifiers.length === 0 ? className : className.slice(modifierStart);
		let baseClassName = baseClassNameWithImportantModifier;
		let hasImportantModifier = false;
		if (baseClassNameWithImportantModifier.endsWith(IMPORTANT_MODIFIER)) {
			baseClassName = baseClassNameWithImportantModifier.slice(0, -1);
			hasImportantModifier = true;
		} else if (baseClassNameWithImportantModifier.startsWith(IMPORTANT_MODIFIER)) {
			baseClassName = baseClassNameWithImportantModifier.slice(1);
			hasImportantModifier = true;
		}
		const maybePostfixModifierPosition = postfixModifierPosition && postfixModifierPosition > modifierStart ? postfixModifierPosition - modifierStart : void 0;
		return createResultObject(modifiers, hasImportantModifier, baseClassName, maybePostfixModifierPosition);
	};
	if (prefix) {
		const fullPrefix = prefix + MODIFIER_SEPARATOR;
		const parseClassNameOriginal = parseClassName;
		parseClassName = (className) => className.startsWith(fullPrefix) ? parseClassNameOriginal(className.slice(fullPrefix.length)) : createResultObject(EMPTY_MODIFIERS, false, className, void 0, true);
	}
	if (experimentalParseClassName) {
		const parseClassNameOriginal = parseClassName;
		parseClassName = (className) => experimentalParseClassName({
			className,
			parseClassName: parseClassNameOriginal
		});
	}
	return parseClassName;
};
/**
* Sorts modifiers according to following schema:
* - Predefined modifiers are sorted alphabetically
* - When an arbitrary variant appears, it must be preserved which modifiers are before and after it
*/
var createSortModifiers = (config) => {
	const modifierWeights = /* @__PURE__ */ new Map();
	config.orderSensitiveModifiers.forEach((mod, index) => {
		modifierWeights.set(mod, 1e6 + index);
	});
	return (modifiers) => {
		const result = [];
		let currentSegment = [];
		for (let i = 0; i < modifiers.length; i++) {
			const modifier = modifiers[i];
			const isArbitrary = modifier[0] === "[";
			const isOrderSensitive = modifierWeights.has(modifier);
			if (isArbitrary || isOrderSensitive) {
				if (currentSegment.length > 0) {
					currentSegment.sort();
					result.push(...currentSegment);
					currentSegment = [];
				}
				result.push(modifier);
			} else currentSegment.push(modifier);
		}
		if (currentSegment.length > 0) {
			currentSegment.sort();
			result.push(...currentSegment);
		}
		return result;
	};
};
var createConfigUtils = (config) => ({
	cache: createLruCache(config.cacheSize),
	parseClassName: createParseClassName(config),
	sortModifiers: createSortModifiers(config),
	postfixLookupClassGroupIds: createPostfixLookupClassGroupIds(config),
	...createClassGroupUtils(config)
});
var createPostfixLookupClassGroupIds = (config) => {
	const lookup = Object.create(null);
	const classGroupIds = config.postfixLookupClassGroups;
	if (classGroupIds) for (let i = 0; i < classGroupIds.length; i++) lookup[classGroupIds[i]] = true;
	return lookup;
};
var SPLIT_CLASSES_REGEX = /\s+/;
var mergeClassList = (classList, configUtils) => {
	const { parseClassName, getClassGroupId, getConflictingClassGroupIds, sortModifiers, postfixLookupClassGroupIds } = configUtils;
	/**
	* Set of classGroupIds in following format:
	* `{importantModifier}{variantModifiers}{classGroupId}`
	* @example 'float'
	* @example 'hover:focus:bg-color'
	* @example 'md:!pr'
	*/
	const classGroupsInConflict = [];
	const classNames = classList.trim().split(SPLIT_CLASSES_REGEX);
	let result = "";
	for (let index = classNames.length - 1; index >= 0; index -= 1) {
		const originalClassName = classNames[index];
		const { isExternal, modifiers, hasImportantModifier, baseClassName, maybePostfixModifierPosition } = parseClassName(originalClassName);
		if (isExternal) {
			result = originalClassName + (result.length > 0 ? " " + result : result);
			continue;
		}
		let hasPostfixModifier = !!maybePostfixModifierPosition;
		let classGroupId;
		if (hasPostfixModifier) {
			classGroupId = getClassGroupId(baseClassName.substring(0, maybePostfixModifierPosition));
			const classGroupIdWithPostfix = classGroupId && postfixLookupClassGroupIds[classGroupId] ? getClassGroupId(baseClassName) : void 0;
			if (classGroupIdWithPostfix && classGroupIdWithPostfix !== classGroupId) {
				classGroupId = classGroupIdWithPostfix;
				hasPostfixModifier = false;
			}
		} else classGroupId = getClassGroupId(baseClassName);
		if (!classGroupId) {
			if (!hasPostfixModifier) {
				result = originalClassName + (result.length > 0 ? " " + result : result);
				continue;
			}
			classGroupId = getClassGroupId(baseClassName);
			if (!classGroupId) {
				result = originalClassName + (result.length > 0 ? " " + result : result);
				continue;
			}
			hasPostfixModifier = false;
		}
		const variantModifier = modifiers.length === 0 ? "" : modifiers.length === 1 ? modifiers[0] : sortModifiers(modifiers).join(":");
		const modifierId = hasImportantModifier ? variantModifier + IMPORTANT_MODIFIER : variantModifier;
		const classId = modifierId + classGroupId;
		if (classGroupsInConflict.indexOf(classId) > -1) continue;
		classGroupsInConflict.push(classId);
		const conflictGroups = getConflictingClassGroupIds(classGroupId, hasPostfixModifier);
		for (let i = 0; i < conflictGroups.length; ++i) {
			const group = conflictGroups[i];
			classGroupsInConflict.push(modifierId + group);
		}
		result = originalClassName + (result.length > 0 ? " " + result : result);
	}
	return result;
};
/**
* The code in this file is copied from https://github.com/lukeed/clsx and modified to suit the needs of tailwind-merge better.
*
* Specifically:
* - Runtime code from https://github.com/lukeed/clsx/blob/v1.2.1/src/index.js
* - TypeScript types from https://github.com/lukeed/clsx/blob/v1.2.1/clsx.d.ts
*
* Original code has MIT license: Copyright (c) Luke Edwards <luke.edwards05@gmail.com> (lukeed.com)
*/
var twJoin = (...classLists) => {
	let index = 0;
	let argument;
	let resolvedValue;
	let string = "";
	while (index < classLists.length) if (argument = classLists[index++]) {
		if (resolvedValue = toValue(argument)) {
			string && (string += " ");
			string += resolvedValue;
		}
	}
	return string;
};
var toValue = (mix) => {
	if (typeof mix === "string") return mix;
	let resolvedValue;
	let string = "";
	for (let k = 0; k < mix.length; k++) if (mix[k]) {
		if (resolvedValue = toValue(mix[k])) {
			string && (string += " ");
			string += resolvedValue;
		}
	}
	return string;
};
var createTailwindMerge = (createConfigFirst, ...createConfigRest) => {
	let configUtils;
	let cacheGet;
	let cacheSet;
	let functionToCall;
	const initTailwindMerge = (classList) => {
		configUtils = createConfigUtils(createConfigRest.reduce((previousConfig, createConfigCurrent) => createConfigCurrent(previousConfig), createConfigFirst()));
		cacheGet = configUtils.cache.get;
		cacheSet = configUtils.cache.set;
		functionToCall = tailwindMerge;
		return tailwindMerge(classList);
	};
	const tailwindMerge = (classList) => {
		const cachedResult = cacheGet(classList);
		if (cachedResult) return cachedResult;
		const result = mergeClassList(classList, configUtils);
		cacheSet(classList, result);
		return result;
	};
	functionToCall = initTailwindMerge;
	return (...args) => functionToCall(twJoin(...args));
};
var fallbackThemeArr = [];
var fromTheme = (key) => {
	const themeGetter = (theme) => theme[key] || fallbackThemeArr;
	themeGetter.isThemeGetter = true;
	return themeGetter;
};
var arbitraryValueRegex = /^\[(?:(\w[\w-]*):)?(.+)\]$/i;
var arbitraryVariableRegex = /^\((?:(\w[\w-]*):)?(.+)\)$/i;
var fractionRegex = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/;
var tshirtUnitRegex = /^(\d+(\.\d+)?)?(xs|sm|md|lg|xl)$/;
var lengthUnitRegex = /\d+(%|px|r?em|[sdl]?v([hwib]|min|max)|pt|pc|in|cm|mm|cap|ch|ex|r?lh|cq(w|h|i|b|min|max))|\b(calc|min|max|clamp)\(.+\)|^0$/;
var colorFunctionRegex = /^(rgba?|hsla?|hwb|(ok)?(lab|lch)|color-mix)\(.+\)$/;
var shadowRegex = /^(inset_)?-?((\d+)?\.?(\d+)[a-z]+|0)_-?((\d+)?\.?(\d+)[a-z]+|0)/;
var imageRegex = /^(url|image|image-set|cross-fade|element|(repeating-)?(linear|radial|conic)-gradient)\(.+\)$/;
var isFraction = (value) => fractionRegex.test(value);
var isNumber = (value) => !!value && !Number.isNaN(Number(value));
var isInteger = (value) => !!value && Number.isInteger(Number(value));
var isPercent = (value) => value.endsWith("%") && isNumber(value.slice(0, -1));
var isTshirtSize = (value) => tshirtUnitRegex.test(value);
var isAny = () => true;
var isLengthOnly = (value) => lengthUnitRegex.test(value) && !colorFunctionRegex.test(value);
var isNever = () => false;
var isShadow = (value) => shadowRegex.test(value);
var isImage = (value) => imageRegex.test(value);
var isAnyNonArbitrary = (value) => !isArbitraryValue(value) && !isArbitraryVariable(value);
var isNamedContainerQuery = (value) => value.startsWith("@container") && (value[10] === "/" && value[11] !== void 0 || value[11] === "s" && value[16] !== void 0 && value.startsWith("-size/", 10) || value[11] === "n" && value[18] !== void 0 && value.startsWith("-normal/", 10));
var isArbitrarySize = (value) => getIsArbitraryValue(value, isLabelSize, isNever);
var isArbitraryValue = (value) => arbitraryValueRegex.test(value);
var isArbitraryLength = (value) => getIsArbitraryValue(value, isLabelLength, isLengthOnly);
var isArbitraryNumber = (value) => getIsArbitraryValue(value, isLabelNumber, isNumber);
var isArbitraryWeight = (value) => getIsArbitraryValue(value, isLabelWeight, isAny);
var isArbitraryFamilyName = (value) => getIsArbitraryValue(value, isLabelFamilyName, isNever);
var isArbitraryPosition = (value) => getIsArbitraryValue(value, isLabelPosition, isNever);
var isArbitraryImage = (value) => getIsArbitraryValue(value, isLabelImage, isImage);
var isArbitraryShadow = (value) => getIsArbitraryValue(value, isLabelShadow, isShadow);
var isArbitraryVariable = (value) => arbitraryVariableRegex.test(value);
var isArbitraryVariableLength = (value) => getIsArbitraryVariable(value, isLabelLength);
var isArbitraryVariableFamilyName = (value) => getIsArbitraryVariable(value, isLabelFamilyName);
var isArbitraryVariablePosition = (value) => getIsArbitraryVariable(value, isLabelPosition);
var isArbitraryVariableSize = (value) => getIsArbitraryVariable(value, isLabelSize);
var isArbitraryVariableImage = (value) => getIsArbitraryVariable(value, isLabelImage);
var isArbitraryVariableShadow = (value) => getIsArbitraryVariable(value, isLabelShadow, true);
var isArbitraryVariableWeight = (value) => getIsArbitraryVariable(value, isLabelWeight, true);
var getIsArbitraryValue = (value, testLabel, testValue) => {
	const result = arbitraryValueRegex.exec(value);
	if (result) {
		if (result[1]) return testLabel(result[1]);
		return testValue(result[2]);
	}
	return false;
};
var getIsArbitraryVariable = (value, testLabel, shouldMatchNoLabel = false) => {
	const result = arbitraryVariableRegex.exec(value);
	if (result) {
		if (result[1]) return testLabel(result[1]);
		return shouldMatchNoLabel;
	}
	return false;
};
var isLabelPosition = (label) => label === "position" || label === "percentage";
var isLabelImage = (label) => label === "image" || label === "url";
var isLabelSize = (label) => label === "length" || label === "size" || label === "bg-size";
var isLabelLength = (label) => label === "length";
var isLabelNumber = (label) => label === "number";
var isLabelFamilyName = (label) => label === "family-name";
var isLabelWeight = (label) => label === "number" || label === "weight";
var isLabelShadow = (label) => label === "shadow";
var getDefaultConfig = () => {
	/**
	* Theme getters for theme variable namespaces
	* @see https://tailwindcss.com/docs/theme#theme-variable-namespaces
	*/
	const themeColor = fromTheme("color");
	const themeFont = fromTheme("font");
	const themeText = fromTheme("text");
	const themeFontWeight = fromTheme("font-weight");
	const themeTracking = fromTheme("tracking");
	const themeLeading = fromTheme("leading");
	const themeBreakpoint = fromTheme("breakpoint");
	const themeContainer = fromTheme("container");
	const themeSpacing = fromTheme("spacing");
	const themeRadius = fromTheme("radius");
	const themeShadow = fromTheme("shadow");
	const themeInsetShadow = fromTheme("inset-shadow");
	const themeTextShadow = fromTheme("text-shadow");
	const themeDropShadow = fromTheme("drop-shadow");
	const themeBlur = fromTheme("blur");
	const themePerspective = fromTheme("perspective");
	const themeAspect = fromTheme("aspect");
	const themeEase = fromTheme("ease");
	const themeAnimate = fromTheme("animate");
	/**
	* Helpers to avoid repeating the same scales
	*
	* We use functions that create a new array every time they're called instead of static arrays.
	* This ensures that users who modify any scale by mutating the array (e.g. with `array.push(element)`) don't accidentally mutate arrays in other parts of the config.
	*/
	const scaleBreak = () => [
		"auto",
		"avoid",
		"all",
		"avoid-page",
		"page",
		"left",
		"right",
		"column"
	];
	const scalePosition = () => [
		"center",
		"top",
		"bottom",
		"left",
		"right",
		"top-left",
		"left-top",
		"top-right",
		"right-top",
		"bottom-right",
		"right-bottom",
		"bottom-left",
		"left-bottom"
	];
	const scalePositionWithArbitrary = () => [
		...scalePosition(),
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleOverflow = () => [
		"auto",
		"hidden",
		"clip",
		"visible",
		"scroll"
	];
	const scaleOverscroll = () => [
		"auto",
		"contain",
		"none"
	];
	const scaleUnambiguousSpacing = () => [
		isArbitraryVariable,
		isArbitraryValue,
		themeSpacing
	];
	const scaleInset = () => [
		isFraction,
		"full",
		"auto",
		...scaleUnambiguousSpacing()
	];
	const scaleGridTemplateColsRows = () => [
		isInteger,
		"none",
		"subgrid",
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleGridColRowStartAndEnd = () => [
		"auto",
		{ span: [
			"full",
			isInteger,
			isArbitraryVariable,
			isArbitraryValue
		] },
		isInteger,
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleGridColRowStartOrEnd = () => [
		isInteger,
		"auto",
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleGridAutoColsRows = () => [
		"auto",
		"min",
		"max",
		"fr",
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleAlignPrimaryAxis = () => [
		"start",
		"end",
		"center",
		"between",
		"around",
		"evenly",
		"stretch",
		"baseline",
		"center-safe",
		"end-safe"
	];
	const scaleAlignSecondaryAxis = () => [
		"start",
		"end",
		"center",
		"stretch",
		"center-safe",
		"end-safe"
	];
	const scaleMargin = () => ["auto", ...scaleUnambiguousSpacing()];
	const scaleSizing = () => [
		isFraction,
		"auto",
		"full",
		"dvw",
		"dvh",
		"lvw",
		"lvh",
		"svw",
		"svh",
		"min",
		"max",
		"fit",
		...scaleUnambiguousSpacing()
	];
	const scaleSizingInline = () => [
		isFraction,
		"screen",
		"full",
		"dvw",
		"lvw",
		"svw",
		"min",
		"max",
		"fit",
		...scaleUnambiguousSpacing()
	];
	const scaleSizingBlock = () => [
		isFraction,
		"screen",
		"full",
		"lh",
		"dvh",
		"lvh",
		"svh",
		"min",
		"max",
		"fit",
		...scaleUnambiguousSpacing()
	];
	const scaleColor = () => [
		themeColor,
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleBgPosition = () => [
		...scalePosition(),
		isArbitraryVariablePosition,
		isArbitraryPosition,
		{ position: [isArbitraryVariable, isArbitraryValue] }
	];
	const scaleBgRepeat = () => ["no-repeat", { repeat: [
		"",
		"x",
		"y",
		"space",
		"round"
	] }];
	const scaleBgSize = () => [
		"auto",
		"cover",
		"contain",
		isArbitraryVariableSize,
		isArbitrarySize,
		{ size: [isArbitraryVariable, isArbitraryValue] }
	];
	const scaleGradientStopPosition = () => [
		isPercent,
		isArbitraryVariableLength,
		isArbitraryLength
	];
	const scaleRadius = () => [
		"",
		"none",
		"full",
		themeRadius,
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleBorderWidth = () => [
		"",
		isNumber,
		isArbitraryVariableLength,
		isArbitraryLength
	];
	const scaleLineStyle = () => [
		"solid",
		"dashed",
		"dotted",
		"double"
	];
	const scaleBlendMode = () => [
		"normal",
		"multiply",
		"screen",
		"overlay",
		"darken",
		"lighten",
		"color-dodge",
		"color-burn",
		"hard-light",
		"soft-light",
		"difference",
		"exclusion",
		"hue",
		"saturation",
		"color",
		"luminosity"
	];
	const scaleMaskImagePosition = () => [
		isNumber,
		isPercent,
		isArbitraryVariablePosition,
		isArbitraryPosition
	];
	const scaleBlur = () => [
		"",
		"none",
		themeBlur,
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleRotate = () => [
		"none",
		isNumber,
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleScale = () => [
		"none",
		isNumber,
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleSkew = () => [
		isNumber,
		isArbitraryVariable,
		isArbitraryValue
	];
	const scaleTranslate = () => [
		isFraction,
		"full",
		...scaleUnambiguousSpacing()
	];
	return {
		cacheSize: 500,
		theme: {
			animate: [
				"spin",
				"ping",
				"pulse",
				"bounce"
			],
			aspect: ["video"],
			blur: [isTshirtSize],
			breakpoint: [isTshirtSize],
			color: [isAny],
			container: [isTshirtSize],
			"drop-shadow": [isTshirtSize],
			ease: [
				"in",
				"out",
				"in-out"
			],
			font: [isAnyNonArbitrary],
			"font-weight": [
				"thin",
				"extralight",
				"light",
				"normal",
				"medium",
				"semibold",
				"bold",
				"extrabold",
				"black"
			],
			"inset-shadow": [isTshirtSize],
			leading: [
				"none",
				"tight",
				"snug",
				"normal",
				"relaxed",
				"loose"
			],
			perspective: [
				"dramatic",
				"near",
				"normal",
				"midrange",
				"distant",
				"none"
			],
			radius: [isTshirtSize],
			shadow: [isTshirtSize],
			spacing: ["px", isNumber],
			text: [isTshirtSize],
			"text-shadow": [isTshirtSize],
			tracking: [
				"tighter",
				"tight",
				"normal",
				"wide",
				"wider",
				"widest"
			]
		},
		classGroups: {
			/**
			* Aspect Ratio
			* @see https://tailwindcss.com/docs/aspect-ratio
			*/
			aspect: [{ aspect: [
				"auto",
				"square",
				isFraction,
				isArbitraryValue,
				isArbitraryVariable,
				themeAspect
			] }],
			/**
			* Container
			* @see https://tailwindcss.com/docs/container
			* @deprecated since Tailwind CSS v4.0.0
			*/
			container: ["container"],
			/**
			* Container Type
			* @see https://tailwindcss.com/docs/responsive-design#container-queries
			*/
			"container-type": [{ "@container": [
				"",
				"normal",
				"size",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Container Name
			* @see https://tailwindcss.com/docs/responsive-design#named-containers
			*/
			"container-named": [isNamedContainerQuery],
			/**
			* Columns
			* @see https://tailwindcss.com/docs/columns
			*/
			columns: [{ columns: [
				isNumber,
				isArbitraryValue,
				isArbitraryVariable,
				themeContainer
			] }],
			/**
			* Break After
			* @see https://tailwindcss.com/docs/break-after
			*/
			"break-after": [{ "break-after": scaleBreak() }],
			/**
			* Break Before
			* @see https://tailwindcss.com/docs/break-before
			*/
			"break-before": [{ "break-before": scaleBreak() }],
			/**
			* Break Inside
			* @see https://tailwindcss.com/docs/break-inside
			*/
			"break-inside": [{ "break-inside": [
				"auto",
				"avoid",
				"avoid-page",
				"avoid-column"
			] }],
			/**
			* Box Decoration Break
			* @see https://tailwindcss.com/docs/box-decoration-break
			*/
			"box-decoration": [{ "box-decoration": ["slice", "clone"] }],
			/**
			* Box Sizing
			* @see https://tailwindcss.com/docs/box-sizing
			*/
			box: [{ box: ["border", "content"] }],
			/**
			* Display
			* @see https://tailwindcss.com/docs/display
			*/
			display: [
				"block",
				"inline-block",
				"inline",
				"flex",
				"inline-flex",
				"table",
				"inline-table",
				"table-caption",
				"table-cell",
				"table-column",
				"table-column-group",
				"table-footer-group",
				"table-header-group",
				"table-row-group",
				"table-row",
				"flow-root",
				"grid",
				"inline-grid",
				"contents",
				"list-item",
				"hidden"
			],
			/**
			* Screen Reader Only
			* @see https://tailwindcss.com/docs/display#screen-reader-only
			*/
			sr: ["sr-only", "not-sr-only"],
			/**
			* Floats
			* @see https://tailwindcss.com/docs/float
			*/
			float: [{ float: [
				"right",
				"left",
				"none",
				"start",
				"end"
			] }],
			/**
			* Clear
			* @see https://tailwindcss.com/docs/clear
			*/
			clear: [{ clear: [
				"left",
				"right",
				"both",
				"none",
				"start",
				"end"
			] }],
			/**
			* Isolation
			* @see https://tailwindcss.com/docs/isolation
			*/
			isolation: ["isolate", "isolation-auto"],
			/**
			* Object Fit
			* @see https://tailwindcss.com/docs/object-fit
			*/
			"object-fit": [{ object: [
				"contain",
				"cover",
				"fill",
				"none",
				"scale-down"
			] }],
			/**
			* Object Position
			* @see https://tailwindcss.com/docs/object-position
			*/
			"object-position": [{ object: scalePositionWithArbitrary() }],
			/**
			* Overflow
			* @see https://tailwindcss.com/docs/overflow
			*/
			overflow: [{ overflow: scaleOverflow() }],
			/**
			* Overflow X
			* @see https://tailwindcss.com/docs/overflow
			*/
			"overflow-x": [{ "overflow-x": scaleOverflow() }],
			/**
			* Overflow Y
			* @see https://tailwindcss.com/docs/overflow
			*/
			"overflow-y": [{ "overflow-y": scaleOverflow() }],
			/**
			* Overscroll Behavior
			* @see https://tailwindcss.com/docs/overscroll-behavior
			*/
			overscroll: [{ overscroll: scaleOverscroll() }],
			/**
			* Overscroll Behavior X
			* @see https://tailwindcss.com/docs/overscroll-behavior
			*/
			"overscroll-x": [{ "overscroll-x": scaleOverscroll() }],
			/**
			* Overscroll Behavior Y
			* @see https://tailwindcss.com/docs/overscroll-behavior
			*/
			"overscroll-y": [{ "overscroll-y": scaleOverscroll() }],
			/**
			* Position
			* @see https://tailwindcss.com/docs/position
			*/
			position: [
				"static",
				"fixed",
				"absolute",
				"relative",
				"sticky"
			],
			/**
			* Inset
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			inset: [{ inset: scaleInset() }],
			/**
			* Inset Inline
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			"inset-x": [{ "inset-x": scaleInset() }],
			/**
			* Inset Block
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			"inset-y": [{ "inset-y": scaleInset() }],
			/**
			* Inset Inline Start
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			* @todo class group will be renamed to `inset-s` in next major release
			*/
			start: [{
				"inset-s": scaleInset(),
				/**
				* @deprecated since Tailwind CSS v4.2.0 in favor of `inset-s-*` utilities.
				* @see https://github.com/tailwindlabs/tailwindcss/pull/19613
				*/
				start: scaleInset()
			}],
			/**
			* Inset Inline End
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			* @todo class group will be renamed to `inset-e` in next major release
			*/
			end: [{
				"inset-e": scaleInset(),
				/**
				* @deprecated since Tailwind CSS v4.2.0 in favor of `inset-e-*` utilities.
				* @see https://github.com/tailwindlabs/tailwindcss/pull/19613
				*/
				end: scaleInset()
			}],
			/**
			* Inset Block Start
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			"inset-bs": [{ "inset-bs": scaleInset() }],
			/**
			* Inset Block End
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			"inset-be": [{ "inset-be": scaleInset() }],
			/**
			* Top
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			top: [{ top: scaleInset() }],
			/**
			* Right
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			right: [{ right: scaleInset() }],
			/**
			* Bottom
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			bottom: [{ bottom: scaleInset() }],
			/**
			* Left
			* @see https://tailwindcss.com/docs/top-right-bottom-left
			*/
			left: [{ left: scaleInset() }],
			/**
			* Visibility
			* @see https://tailwindcss.com/docs/visibility
			*/
			visibility: [
				"visible",
				"invisible",
				"collapse"
			],
			/**
			* Z-Index
			* @see https://tailwindcss.com/docs/z-index
			*/
			z: [{ z: [
				isInteger,
				"auto",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Flex Basis
			* @see https://tailwindcss.com/docs/flex-basis
			*/
			basis: [{ basis: [
				isFraction,
				"full",
				"auto",
				themeContainer,
				...scaleUnambiguousSpacing()
			] }],
			/**
			* Flex Direction
			* @see https://tailwindcss.com/docs/flex-direction
			*/
			"flex-direction": [{ flex: [
				"row",
				"row-reverse",
				"col",
				"col-reverse"
			] }],
			/**
			* Flex Wrap
			* @see https://tailwindcss.com/docs/flex-wrap
			*/
			"flex-wrap": [{ flex: [
				"nowrap",
				"wrap",
				"wrap-reverse"
			] }],
			/**
			* Flex
			* @see https://tailwindcss.com/docs/flex
			*/
			flex: [{ flex: [
				isNumber,
				isFraction,
				"auto",
				"initial",
				"none",
				isArbitraryValue
			] }],
			/**
			* Flex Grow
			* @see https://tailwindcss.com/docs/flex-grow
			*/
			grow: [{ grow: [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Flex Shrink
			* @see https://tailwindcss.com/docs/flex-shrink
			*/
			shrink: [{ shrink: [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Order
			* @see https://tailwindcss.com/docs/order
			*/
			order: [{ order: [
				isInteger,
				"first",
				"last",
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Grid Template Columns
			* @see https://tailwindcss.com/docs/grid-template-columns
			*/
			"grid-cols": [{ "grid-cols": scaleGridTemplateColsRows() }],
			/**
			* Grid Column Start / End
			* @see https://tailwindcss.com/docs/grid-column
			*/
			"col-start-end": [{ col: scaleGridColRowStartAndEnd() }],
			/**
			* Grid Column Start
			* @see https://tailwindcss.com/docs/grid-column
			*/
			"col-start": [{ "col-start": scaleGridColRowStartOrEnd() }],
			/**
			* Grid Column End
			* @see https://tailwindcss.com/docs/grid-column
			*/
			"col-end": [{ "col-end": scaleGridColRowStartOrEnd() }],
			/**
			* Grid Template Rows
			* @see https://tailwindcss.com/docs/grid-template-rows
			*/
			"grid-rows": [{ "grid-rows": scaleGridTemplateColsRows() }],
			/**
			* Grid Row Start / End
			* @see https://tailwindcss.com/docs/grid-row
			*/
			"row-start-end": [{ row: scaleGridColRowStartAndEnd() }],
			/**
			* Grid Row Start
			* @see https://tailwindcss.com/docs/grid-row
			*/
			"row-start": [{ "row-start": scaleGridColRowStartOrEnd() }],
			/**
			* Grid Row End
			* @see https://tailwindcss.com/docs/grid-row
			*/
			"row-end": [{ "row-end": scaleGridColRowStartOrEnd() }],
			/**
			* Grid Auto Flow
			* @see https://tailwindcss.com/docs/grid-auto-flow
			*/
			"grid-flow": [{ "grid-flow": [
				"row",
				"col",
				"dense",
				"row-dense",
				"col-dense"
			] }],
			/**
			* Grid Auto Columns
			* @see https://tailwindcss.com/docs/grid-auto-columns
			*/
			"auto-cols": [{ "auto-cols": scaleGridAutoColsRows() }],
			/**
			* Grid Auto Rows
			* @see https://tailwindcss.com/docs/grid-auto-rows
			*/
			"auto-rows": [{ "auto-rows": scaleGridAutoColsRows() }],
			/**
			* Gap
			* @see https://tailwindcss.com/docs/gap
			*/
			gap: [{ gap: scaleUnambiguousSpacing() }],
			/**
			* Gap X
			* @see https://tailwindcss.com/docs/gap
			*/
			"gap-x": [{ "gap-x": scaleUnambiguousSpacing() }],
			/**
			* Gap Y
			* @see https://tailwindcss.com/docs/gap
			*/
			"gap-y": [{ "gap-y": scaleUnambiguousSpacing() }],
			/**
			* Justify Content
			* @see https://tailwindcss.com/docs/justify-content
			*/
			"justify-content": [{ justify: [...scaleAlignPrimaryAxis(), "normal"] }],
			/**
			* Justify Items
			* @see https://tailwindcss.com/docs/justify-items
			*/
			"justify-items": [{ "justify-items": [...scaleAlignSecondaryAxis(), "normal"] }],
			/**
			* Justify Self
			* @see https://tailwindcss.com/docs/justify-self
			*/
			"justify-self": [{ "justify-self": ["auto", ...scaleAlignSecondaryAxis()] }],
			/**
			* Align Content
			* @see https://tailwindcss.com/docs/align-content
			*/
			"align-content": [{ content: ["normal", ...scaleAlignPrimaryAxis()] }],
			/**
			* Align Items
			* @see https://tailwindcss.com/docs/align-items
			*/
			"align-items": [{ items: [...scaleAlignSecondaryAxis(), { baseline: ["", "last"] }] }],
			/**
			* Align Self
			* @see https://tailwindcss.com/docs/align-self
			*/
			"align-self": [{ self: [
				"auto",
				...scaleAlignSecondaryAxis(),
				{ baseline: ["", "last"] }
			] }],
			/**
			* Place Content
			* @see https://tailwindcss.com/docs/place-content
			*/
			"place-content": [{ "place-content": scaleAlignPrimaryAxis() }],
			/**
			* Place Items
			* @see https://tailwindcss.com/docs/place-items
			*/
			"place-items": [{ "place-items": [...scaleAlignSecondaryAxis(), "baseline"] }],
			/**
			* Place Self
			* @see https://tailwindcss.com/docs/place-self
			*/
			"place-self": [{ "place-self": ["auto", ...scaleAlignSecondaryAxis()] }],
			/**
			* Padding
			* @see https://tailwindcss.com/docs/padding
			*/
			p: [{ p: scaleUnambiguousSpacing() }],
			/**
			* Padding Inline
			* @see https://tailwindcss.com/docs/padding
			*/
			px: [{ px: scaleUnambiguousSpacing() }],
			/**
			* Padding Block
			* @see https://tailwindcss.com/docs/padding
			*/
			py: [{ py: scaleUnambiguousSpacing() }],
			/**
			* Padding Inline Start
			* @see https://tailwindcss.com/docs/padding
			*/
			ps: [{ ps: scaleUnambiguousSpacing() }],
			/**
			* Padding Inline End
			* @see https://tailwindcss.com/docs/padding
			*/
			pe: [{ pe: scaleUnambiguousSpacing() }],
			/**
			* Padding Block Start
			* @see https://tailwindcss.com/docs/padding
			*/
			pbs: [{ pbs: scaleUnambiguousSpacing() }],
			/**
			* Padding Block End
			* @see https://tailwindcss.com/docs/padding
			*/
			pbe: [{ pbe: scaleUnambiguousSpacing() }],
			/**
			* Padding Top
			* @see https://tailwindcss.com/docs/padding
			*/
			pt: [{ pt: scaleUnambiguousSpacing() }],
			/**
			* Padding Right
			* @see https://tailwindcss.com/docs/padding
			*/
			pr: [{ pr: scaleUnambiguousSpacing() }],
			/**
			* Padding Bottom
			* @see https://tailwindcss.com/docs/padding
			*/
			pb: [{ pb: scaleUnambiguousSpacing() }],
			/**
			* Padding Left
			* @see https://tailwindcss.com/docs/padding
			*/
			pl: [{ pl: scaleUnambiguousSpacing() }],
			/**
			* Margin
			* @see https://tailwindcss.com/docs/margin
			*/
			m: [{ m: scaleMargin() }],
			/**
			* Margin Inline
			* @see https://tailwindcss.com/docs/margin
			*/
			mx: [{ mx: scaleMargin() }],
			/**
			* Margin Block
			* @see https://tailwindcss.com/docs/margin
			*/
			my: [{ my: scaleMargin() }],
			/**
			* Margin Inline Start
			* @see https://tailwindcss.com/docs/margin
			*/
			ms: [{ ms: scaleMargin() }],
			/**
			* Margin Inline End
			* @see https://tailwindcss.com/docs/margin
			*/
			me: [{ me: scaleMargin() }],
			/**
			* Margin Block Start
			* @see https://tailwindcss.com/docs/margin
			*/
			mbs: [{ mbs: scaleMargin() }],
			/**
			* Margin Block End
			* @see https://tailwindcss.com/docs/margin
			*/
			mbe: [{ mbe: scaleMargin() }],
			/**
			* Margin Top
			* @see https://tailwindcss.com/docs/margin
			*/
			mt: [{ mt: scaleMargin() }],
			/**
			* Margin Right
			* @see https://tailwindcss.com/docs/margin
			*/
			mr: [{ mr: scaleMargin() }],
			/**
			* Margin Bottom
			* @see https://tailwindcss.com/docs/margin
			*/
			mb: [{ mb: scaleMargin() }],
			/**
			* Margin Left
			* @see https://tailwindcss.com/docs/margin
			*/
			ml: [{ ml: scaleMargin() }],
			/**
			* Space Between X
			* @see https://tailwindcss.com/docs/margin#adding-space-between-children
			*/
			"space-x": [{ "space-x": scaleUnambiguousSpacing() }],
			/**
			* Space Between X Reverse
			* @see https://tailwindcss.com/docs/margin#adding-space-between-children
			*/
			"space-x-reverse": ["space-x-reverse"],
			/**
			* Space Between Y
			* @see https://tailwindcss.com/docs/margin#adding-space-between-children
			*/
			"space-y": [{ "space-y": scaleUnambiguousSpacing() }],
			/**
			* Space Between Y Reverse
			* @see https://tailwindcss.com/docs/margin#adding-space-between-children
			*/
			"space-y-reverse": ["space-y-reverse"],
			/**
			* Size
			* @see https://tailwindcss.com/docs/width#setting-both-width-and-height
			*/
			size: [{ size: scaleSizing() }],
			/**
			* Inline Size
			* @see https://tailwindcss.com/docs/width
			*/
			"inline-size": [{ inline: ["auto", ...scaleSizingInline()] }],
			/**
			* Min-Inline Size
			* @see https://tailwindcss.com/docs/min-width
			*/
			"min-inline-size": [{ "min-inline": ["auto", ...scaleSizingInline()] }],
			/**
			* Max-Inline Size
			* @see https://tailwindcss.com/docs/max-width
			*/
			"max-inline-size": [{ "max-inline": ["none", ...scaleSizingInline()] }],
			/**
			* Block Size
			* @see https://tailwindcss.com/docs/height
			*/
			"block-size": [{ block: ["auto", ...scaleSizingBlock()] }],
			/**
			* Min-Block Size
			* @see https://tailwindcss.com/docs/min-height
			*/
			"min-block-size": [{ "min-block": ["auto", ...scaleSizingBlock()] }],
			/**
			* Max-Block Size
			* @see https://tailwindcss.com/docs/max-height
			*/
			"max-block-size": [{ "max-block": ["none", ...scaleSizingBlock()] }],
			/**
			* Width
			* @see https://tailwindcss.com/docs/width
			*/
			w: [{ w: [
				themeContainer,
				"screen",
				...scaleSizing()
			] }],
			/**
			* Min-Width
			* @see https://tailwindcss.com/docs/min-width
			*/
			"min-w": [{ "min-w": [
				themeContainer,
				"screen",
				"none",
				...scaleSizing()
			] }],
			/**
			* Max-Width
			* @see https://tailwindcss.com/docs/max-width
			*/
			"max-w": [{ "max-w": [
				themeContainer,
				"screen",
				"none",
				"prose",
				{ screen: [themeBreakpoint] },
				...scaleSizing()
			] }],
			/**
			* Height
			* @see https://tailwindcss.com/docs/height
			*/
			h: [{ h: [
				"screen",
				"lh",
				...scaleSizing()
			] }],
			/**
			* Min-Height
			* @see https://tailwindcss.com/docs/min-height
			*/
			"min-h": [{ "min-h": [
				"screen",
				"lh",
				"none",
				...scaleSizing()
			] }],
			/**
			* Max-Height
			* @see https://tailwindcss.com/docs/max-height
			*/
			"max-h": [{ "max-h": [
				"screen",
				"lh",
				...scaleSizing()
			] }],
			/**
			* Font Size
			* @see https://tailwindcss.com/docs/font-size
			*/
			"font-size": [{ text: [
				"base",
				themeText,
				isArbitraryVariableLength,
				isArbitraryLength
			] }],
			/**
			* Font Smoothing
			* @see https://tailwindcss.com/docs/font-smoothing
			*/
			"font-smoothing": ["antialiased", "subpixel-antialiased"],
			/**
			* Font Style
			* @see https://tailwindcss.com/docs/font-style
			*/
			"font-style": ["italic", "not-italic"],
			/**
			* Font Weight
			* @see https://tailwindcss.com/docs/font-weight
			*/
			"font-weight": [{ font: [
				themeFontWeight,
				isArbitraryVariableWeight,
				isArbitraryWeight
			] }],
			/**
			* Font Stretch
			* @see https://tailwindcss.com/docs/font-stretch
			*/
			"font-stretch": [{ "font-stretch": [
				"ultra-condensed",
				"extra-condensed",
				"condensed",
				"semi-condensed",
				"normal",
				"semi-expanded",
				"expanded",
				"extra-expanded",
				"ultra-expanded",
				isPercent,
				isArbitraryValue
			] }],
			/**
			* Font Family
			* @see https://tailwindcss.com/docs/font-family
			*/
			"font-family": [{ font: [
				isArbitraryVariableFamilyName,
				isArbitraryFamilyName,
				themeFont
			] }],
			/**
			* Font Feature Settings
			* @see https://tailwindcss.com/docs/font-feature-settings
			*/
			"font-features": [{ "font-features": [isArbitraryValue] }],
			/**
			* Font Variant Numeric
			* @see https://tailwindcss.com/docs/font-variant-numeric
			*/
			"fvn-normal": ["normal-nums"],
			/**
			* Font Variant Numeric
			* @see https://tailwindcss.com/docs/font-variant-numeric
			*/
			"fvn-ordinal": ["ordinal"],
			/**
			* Font Variant Numeric
			* @see https://tailwindcss.com/docs/font-variant-numeric
			*/
			"fvn-slashed-zero": ["slashed-zero"],
			/**
			* Font Variant Numeric
			* @see https://tailwindcss.com/docs/font-variant-numeric
			*/
			"fvn-figure": ["lining-nums", "oldstyle-nums"],
			/**
			* Font Variant Numeric
			* @see https://tailwindcss.com/docs/font-variant-numeric
			*/
			"fvn-spacing": ["proportional-nums", "tabular-nums"],
			/**
			* Font Variant Numeric
			* @see https://tailwindcss.com/docs/font-variant-numeric
			*/
			"fvn-fraction": ["diagonal-fractions", "stacked-fractions"],
			/**
			* Letter Spacing
			* @see https://tailwindcss.com/docs/letter-spacing
			*/
			tracking: [{ tracking: [
				themeTracking,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Line Clamp
			* @see https://tailwindcss.com/docs/line-clamp
			*/
			"line-clamp": [{ "line-clamp": [
				isNumber,
				"none",
				isArbitraryVariable,
				isArbitraryNumber
			] }],
			/**
			* Line Height
			* @see https://tailwindcss.com/docs/line-height
			*/
			leading: [{ leading: [themeLeading, ...scaleUnambiguousSpacing()] }],
			/**
			* List Style Image
			* @see https://tailwindcss.com/docs/list-style-image
			*/
			"list-image": [{ "list-image": [
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* List Style Position
			* @see https://tailwindcss.com/docs/list-style-position
			*/
			"list-style-position": [{ list: ["inside", "outside"] }],
			/**
			* List Style Type
			* @see https://tailwindcss.com/docs/list-style-type
			*/
			"list-style-type": [{ list: [
				"disc",
				"decimal",
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Text Alignment
			* @see https://tailwindcss.com/docs/text-align
			*/
			"text-alignment": [{ text: [
				"left",
				"center",
				"right",
				"justify",
				"start",
				"end"
			] }],
			/**
			* Placeholder Color
			* @deprecated since Tailwind CSS v3.0.0
			* @see https://v3.tailwindcss.com/docs/placeholder-color
			*/
			"placeholder-color": [{ placeholder: scaleColor() }],
			/**
			* Text Color
			* @see https://tailwindcss.com/docs/text-color
			*/
			"text-color": [{ text: scaleColor() }],
			/**
			* Text Decoration
			* @see https://tailwindcss.com/docs/text-decoration
			*/
			"text-decoration": [
				"underline",
				"overline",
				"line-through",
				"no-underline"
			],
			/**
			* Text Decoration Style
			* @see https://tailwindcss.com/docs/text-decoration-style
			*/
			"text-decoration-style": [{ decoration: [...scaleLineStyle(), "wavy"] }],
			/**
			* Text Decoration Thickness
			* @see https://tailwindcss.com/docs/text-decoration-thickness
			*/
			"text-decoration-thickness": [{ decoration: [
				isNumber,
				"from-font",
				"auto",
				isArbitraryVariable,
				isArbitraryLength
			] }],
			/**
			* Text Decoration Color
			* @see https://tailwindcss.com/docs/text-decoration-color
			*/
			"text-decoration-color": [{ decoration: scaleColor() }],
			/**
			* Text Underline Offset
			* @see https://tailwindcss.com/docs/text-underline-offset
			*/
			"underline-offset": [{ "underline-offset": [
				isNumber,
				"auto",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Text Transform
			* @see https://tailwindcss.com/docs/text-transform
			*/
			"text-transform": [
				"uppercase",
				"lowercase",
				"capitalize",
				"normal-case"
			],
			/**
			* Text Overflow
			* @see https://tailwindcss.com/docs/text-overflow
			*/
			"text-overflow": [
				"truncate",
				"text-ellipsis",
				"text-clip"
			],
			/**
			* Text Wrap
			* @see https://tailwindcss.com/docs/text-wrap
			*/
			"text-wrap": [{ text: [
				"wrap",
				"nowrap",
				"balance",
				"pretty"
			] }],
			/**
			* Text Indent
			* @see https://tailwindcss.com/docs/text-indent
			*/
			indent: [{ indent: scaleUnambiguousSpacing() }],
			/**
			* Tab Size
			* @see https://tailwindcss.com/docs/tab-size
			*/
			"tab-size": [{ tab: [
				isInteger,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Vertical Alignment
			* @see https://tailwindcss.com/docs/vertical-align
			*/
			"vertical-align": [{ align: [
				"baseline",
				"top",
				"middle",
				"bottom",
				"text-top",
				"text-bottom",
				"sub",
				"super",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Whitespace
			* @see https://tailwindcss.com/docs/whitespace
			*/
			whitespace: [{ whitespace: [
				"normal",
				"nowrap",
				"pre",
				"pre-line",
				"pre-wrap",
				"break-spaces"
			] }],
			/**
			* Word Break
			* @see https://tailwindcss.com/docs/word-break
			*/
			break: [{ break: [
				"normal",
				"words",
				"all",
				"keep"
			] }],
			/**
			* Overflow Wrap
			* @see https://tailwindcss.com/docs/overflow-wrap
			*/
			wrap: [{ wrap: [
				"break-word",
				"anywhere",
				"normal"
			] }],
			/**
			* Hyphens
			* @see https://tailwindcss.com/docs/hyphens
			*/
			hyphens: [{ hyphens: [
				"none",
				"manual",
				"auto"
			] }],
			/**
			* Content
			* @see https://tailwindcss.com/docs/content
			*/
			content: [{ content: [
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Background Attachment
			* @see https://tailwindcss.com/docs/background-attachment
			*/
			"bg-attachment": [{ bg: [
				"fixed",
				"local",
				"scroll"
			] }],
			/**
			* Background Clip
			* @see https://tailwindcss.com/docs/background-clip
			*/
			"bg-clip": [{ "bg-clip": [
				"border",
				"padding",
				"content",
				"text"
			] }],
			/**
			* Background Origin
			* @see https://tailwindcss.com/docs/background-origin
			*/
			"bg-origin": [{ "bg-origin": [
				"border",
				"padding",
				"content"
			] }],
			/**
			* Background Position
			* @see https://tailwindcss.com/docs/background-position
			*/
			"bg-position": [{ bg: scaleBgPosition() }],
			/**
			* Background Repeat
			* @see https://tailwindcss.com/docs/background-repeat
			*/
			"bg-repeat": [{ bg: scaleBgRepeat() }],
			/**
			* Background Size
			* @see https://tailwindcss.com/docs/background-size
			*/
			"bg-size": [{ bg: scaleBgSize() }],
			/**
			* Background Image
			* @see https://tailwindcss.com/docs/background-image
			*/
			"bg-image": [{ bg: [
				"none",
				{
					linear: [
						{ to: [
							"t",
							"tr",
							"r",
							"br",
							"b",
							"bl",
							"l",
							"tl"
						] },
						isInteger,
						isArbitraryVariable,
						isArbitraryValue
					],
					radial: [
						"",
						isArbitraryVariable,
						isArbitraryValue
					],
					conic: [
						isInteger,
						isArbitraryVariable,
						isArbitraryValue
					]
				},
				isArbitraryVariableImage,
				isArbitraryImage
			] }],
			/**
			* Background Color
			* @see https://tailwindcss.com/docs/background-color
			*/
			"bg-color": [{ bg: scaleColor() }],
			/**
			* Gradient Color Stops From Position
			* @see https://tailwindcss.com/docs/gradient-color-stops
			*/
			"gradient-from-pos": [{ from: scaleGradientStopPosition() }],
			/**
			* Gradient Color Stops Via Position
			* @see https://tailwindcss.com/docs/gradient-color-stops
			*/
			"gradient-via-pos": [{ via: scaleGradientStopPosition() }],
			/**
			* Gradient Color Stops To Position
			* @see https://tailwindcss.com/docs/gradient-color-stops
			*/
			"gradient-to-pos": [{ to: scaleGradientStopPosition() }],
			/**
			* Gradient Color Stops From
			* @see https://tailwindcss.com/docs/gradient-color-stops
			*/
			"gradient-from": [{ from: scaleColor() }],
			/**
			* Gradient Color Stops Via
			* @see https://tailwindcss.com/docs/gradient-color-stops
			*/
			"gradient-via": [{ via: scaleColor() }],
			/**
			* Gradient Color Stops To
			* @see https://tailwindcss.com/docs/gradient-color-stops
			*/
			"gradient-to": [{ to: scaleColor() }],
			/**
			* Border Radius
			* @see https://tailwindcss.com/docs/border-radius
			*/
			rounded: [{ rounded: scaleRadius() }],
			/**
			* Border Radius Start
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-s": [{ "rounded-s": scaleRadius() }],
			/**
			* Border Radius End
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-e": [{ "rounded-e": scaleRadius() }],
			/**
			* Border Radius Top
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-t": [{ "rounded-t": scaleRadius() }],
			/**
			* Border Radius Right
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-r": [{ "rounded-r": scaleRadius() }],
			/**
			* Border Radius Bottom
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-b": [{ "rounded-b": scaleRadius() }],
			/**
			* Border Radius Left
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-l": [{ "rounded-l": scaleRadius() }],
			/**
			* Border Radius Start Start
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-ss": [{ "rounded-ss": scaleRadius() }],
			/**
			* Border Radius Start End
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-se": [{ "rounded-se": scaleRadius() }],
			/**
			* Border Radius End End
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-ee": [{ "rounded-ee": scaleRadius() }],
			/**
			* Border Radius End Start
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-es": [{ "rounded-es": scaleRadius() }],
			/**
			* Border Radius Top Left
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-tl": [{ "rounded-tl": scaleRadius() }],
			/**
			* Border Radius Top Right
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-tr": [{ "rounded-tr": scaleRadius() }],
			/**
			* Border Radius Bottom Right
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-br": [{ "rounded-br": scaleRadius() }],
			/**
			* Border Radius Bottom Left
			* @see https://tailwindcss.com/docs/border-radius
			*/
			"rounded-bl": [{ "rounded-bl": scaleRadius() }],
			/**
			* Border Width
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w": [{ border: scaleBorderWidth() }],
			/**
			* Border Width Inline
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-x": [{ "border-x": scaleBorderWidth() }],
			/**
			* Border Width Block
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-y": [{ "border-y": scaleBorderWidth() }],
			/**
			* Border Width Inline Start
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-s": [{ "border-s": scaleBorderWidth() }],
			/**
			* Border Width Inline End
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-e": [{ "border-e": scaleBorderWidth() }],
			/**
			* Border Width Block Start
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-bs": [{ "border-bs": scaleBorderWidth() }],
			/**
			* Border Width Block End
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-be": [{ "border-be": scaleBorderWidth() }],
			/**
			* Border Width Top
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-t": [{ "border-t": scaleBorderWidth() }],
			/**
			* Border Width Right
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-r": [{ "border-r": scaleBorderWidth() }],
			/**
			* Border Width Bottom
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-b": [{ "border-b": scaleBorderWidth() }],
			/**
			* Border Width Left
			* @see https://tailwindcss.com/docs/border-width
			*/
			"border-w-l": [{ "border-l": scaleBorderWidth() }],
			/**
			* Divide Width X
			* @see https://tailwindcss.com/docs/border-width#between-children
			*/
			"divide-x": [{ "divide-x": scaleBorderWidth() }],
			/**
			* Divide Width X Reverse
			* @see https://tailwindcss.com/docs/border-width#between-children
			*/
			"divide-x-reverse": ["divide-x-reverse"],
			/**
			* Divide Width Y
			* @see https://tailwindcss.com/docs/border-width#between-children
			*/
			"divide-y": [{ "divide-y": scaleBorderWidth() }],
			/**
			* Divide Width Y Reverse
			* @see https://tailwindcss.com/docs/border-width#between-children
			*/
			"divide-y-reverse": ["divide-y-reverse"],
			/**
			* Border Style
			* @see https://tailwindcss.com/docs/border-style
			*/
			"border-style": [{ border: [
				...scaleLineStyle(),
				"hidden",
				"none"
			] }],
			/**
			* Divide Style
			* @see https://tailwindcss.com/docs/border-style#setting-the-divider-style
			*/
			"divide-style": [{ divide: [
				...scaleLineStyle(),
				"hidden",
				"none"
			] }],
			/**
			* Border Color
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color": [{ border: scaleColor() }],
			/**
			* Border Color Inline
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-x": [{ "border-x": scaleColor() }],
			/**
			* Border Color Block
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-y": [{ "border-y": scaleColor() }],
			/**
			* Border Color Inline Start
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-s": [{ "border-s": scaleColor() }],
			/**
			* Border Color Inline End
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-e": [{ "border-e": scaleColor() }],
			/**
			* Border Color Block Start
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-bs": [{ "border-bs": scaleColor() }],
			/**
			* Border Color Block End
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-be": [{ "border-be": scaleColor() }],
			/**
			* Border Color Top
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-t": [{ "border-t": scaleColor() }],
			/**
			* Border Color Right
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-r": [{ "border-r": scaleColor() }],
			/**
			* Border Color Bottom
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-b": [{ "border-b": scaleColor() }],
			/**
			* Border Color Left
			* @see https://tailwindcss.com/docs/border-color
			*/
			"border-color-l": [{ "border-l": scaleColor() }],
			/**
			* Divide Color
			* @see https://tailwindcss.com/docs/divide-color
			*/
			"divide-color": [{ divide: scaleColor() }],
			/**
			* Outline Style
			* @see https://tailwindcss.com/docs/outline-style
			*/
			"outline-style": [{ outline: [
				...scaleLineStyle(),
				"none",
				"hidden"
			] }],
			/**
			* Outline Offset
			* @see https://tailwindcss.com/docs/outline-offset
			*/
			"outline-offset": [{ "outline-offset": [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Outline Width
			* @see https://tailwindcss.com/docs/outline-width
			*/
			"outline-w": [{ outline: [
				"",
				isNumber,
				isArbitraryVariableLength,
				isArbitraryLength
			] }],
			/**
			* Outline Color
			* @see https://tailwindcss.com/docs/outline-color
			*/
			"outline-color": [{ outline: scaleColor() }],
			/**
			* Box Shadow
			* @see https://tailwindcss.com/docs/box-shadow
			*/
			shadow: [{ shadow: [
				"",
				"none",
				themeShadow,
				isArbitraryVariableShadow,
				isArbitraryShadow
			] }],
			/**
			* Box Shadow Color
			* @see https://tailwindcss.com/docs/box-shadow#setting-the-shadow-color
			*/
			"shadow-color": [{ shadow: scaleColor() }],
			/**
			* Inset Box Shadow
			* @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-shadow
			*/
			"inset-shadow": [{ "inset-shadow": [
				"none",
				themeInsetShadow,
				isArbitraryVariableShadow,
				isArbitraryShadow
			] }],
			/**
			* Inset Box Shadow Color
			* @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-shadow-color
			*/
			"inset-shadow-color": [{ "inset-shadow": scaleColor() }],
			/**
			* Ring Width
			* @see https://tailwindcss.com/docs/box-shadow#adding-a-ring
			*/
			"ring-w": [{ ring: scaleBorderWidth() }],
			/**
			* Ring Width Inset
			* @see https://v3.tailwindcss.com/docs/ring-width#inset-rings
			* @deprecated since Tailwind CSS v4.0.0
			* @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
			*/
			"ring-w-inset": ["ring-inset"],
			/**
			* Ring Color
			* @see https://tailwindcss.com/docs/box-shadow#setting-the-ring-color
			*/
			"ring-color": [{ ring: scaleColor() }],
			/**
			* Ring Offset Width
			* @see https://v3.tailwindcss.com/docs/ring-offset-width
			* @deprecated since Tailwind CSS v4.0.0
			* @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
			*/
			"ring-offset-w": [{ "ring-offset": [isNumber, isArbitraryLength] }],
			/**
			* Ring Offset Color
			* @see https://v3.tailwindcss.com/docs/ring-offset-color
			* @deprecated since Tailwind CSS v4.0.0
			* @see https://github.com/tailwindlabs/tailwindcss/blob/v4.0.0/packages/tailwindcss/src/utilities.ts#L4158
			*/
			"ring-offset-color": [{ "ring-offset": scaleColor() }],
			/**
			* Inset Ring Width
			* @see https://tailwindcss.com/docs/box-shadow#adding-an-inset-ring
			*/
			"inset-ring-w": [{ "inset-ring": scaleBorderWidth() }],
			/**
			* Inset Ring Color
			* @see https://tailwindcss.com/docs/box-shadow#setting-the-inset-ring-color
			*/
			"inset-ring-color": [{ "inset-ring": scaleColor() }],
			/**
			* Text Shadow
			* @see https://tailwindcss.com/docs/text-shadow
			*/
			"text-shadow": [{ "text-shadow": [
				"none",
				themeTextShadow,
				isArbitraryVariableShadow,
				isArbitraryShadow
			] }],
			/**
			* Text Shadow Color
			* @see https://tailwindcss.com/docs/text-shadow#setting-the-shadow-color
			*/
			"text-shadow-color": [{ "text-shadow": scaleColor() }],
			/**
			* Opacity
			* @see https://tailwindcss.com/docs/opacity
			*/
			opacity: [{ opacity: [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Mix Blend Mode
			* @see https://tailwindcss.com/docs/mix-blend-mode
			*/
			"mix-blend": [{ "mix-blend": [
				...scaleBlendMode(),
				"plus-darker",
				"plus-lighter"
			] }],
			/**
			* Background Blend Mode
			* @see https://tailwindcss.com/docs/background-blend-mode
			*/
			"bg-blend": [{ "bg-blend": scaleBlendMode() }],
			/**
			* Mask Clip
			* @see https://tailwindcss.com/docs/mask-clip
			*/
			"mask-clip": [{ "mask-clip": [
				"border",
				"padding",
				"content",
				"fill",
				"stroke",
				"view"
			] }, "mask-no-clip"],
			/**
			* Mask Composite
			* @see https://tailwindcss.com/docs/mask-composite
			*/
			"mask-composite": [{ mask: [
				"add",
				"subtract",
				"intersect",
				"exclude"
			] }],
			/**
			* Mask Image
			* @see https://tailwindcss.com/docs/mask-image
			*/
			"mask-image-linear-pos": [{ "mask-linear": [isNumber] }],
			"mask-image-linear-from-pos": [{ "mask-linear-from": scaleMaskImagePosition() }],
			"mask-image-linear-to-pos": [{ "mask-linear-to": scaleMaskImagePosition() }],
			"mask-image-linear-from-color": [{ "mask-linear-from": scaleColor() }],
			"mask-image-linear-to-color": [{ "mask-linear-to": scaleColor() }],
			"mask-image-t-from-pos": [{ "mask-t-from": scaleMaskImagePosition() }],
			"mask-image-t-to-pos": [{ "mask-t-to": scaleMaskImagePosition() }],
			"mask-image-t-from-color": [{ "mask-t-from": scaleColor() }],
			"mask-image-t-to-color": [{ "mask-t-to": scaleColor() }],
			"mask-image-r-from-pos": [{ "mask-r-from": scaleMaskImagePosition() }],
			"mask-image-r-to-pos": [{ "mask-r-to": scaleMaskImagePosition() }],
			"mask-image-r-from-color": [{ "mask-r-from": scaleColor() }],
			"mask-image-r-to-color": [{ "mask-r-to": scaleColor() }],
			"mask-image-b-from-pos": [{ "mask-b-from": scaleMaskImagePosition() }],
			"mask-image-b-to-pos": [{ "mask-b-to": scaleMaskImagePosition() }],
			"mask-image-b-from-color": [{ "mask-b-from": scaleColor() }],
			"mask-image-b-to-color": [{ "mask-b-to": scaleColor() }],
			"mask-image-l-from-pos": [{ "mask-l-from": scaleMaskImagePosition() }],
			"mask-image-l-to-pos": [{ "mask-l-to": scaleMaskImagePosition() }],
			"mask-image-l-from-color": [{ "mask-l-from": scaleColor() }],
			"mask-image-l-to-color": [{ "mask-l-to": scaleColor() }],
			"mask-image-x-from-pos": [{ "mask-x-from": scaleMaskImagePosition() }],
			"mask-image-x-to-pos": [{ "mask-x-to": scaleMaskImagePosition() }],
			"mask-image-x-from-color": [{ "mask-x-from": scaleColor() }],
			"mask-image-x-to-color": [{ "mask-x-to": scaleColor() }],
			"mask-image-y-from-pos": [{ "mask-y-from": scaleMaskImagePosition() }],
			"mask-image-y-to-pos": [{ "mask-y-to": scaleMaskImagePosition() }],
			"mask-image-y-from-color": [{ "mask-y-from": scaleColor() }],
			"mask-image-y-to-color": [{ "mask-y-to": scaleColor() }],
			"mask-image-radial": [{ "mask-radial": [isArbitraryVariable, isArbitraryValue] }],
			"mask-image-radial-from-pos": [{ "mask-radial-from": scaleMaskImagePosition() }],
			"mask-image-radial-to-pos": [{ "mask-radial-to": scaleMaskImagePosition() }],
			"mask-image-radial-from-color": [{ "mask-radial-from": scaleColor() }],
			"mask-image-radial-to-color": [{ "mask-radial-to": scaleColor() }],
			"mask-image-radial-shape": [{ "mask-radial": ["circle", "ellipse"] }],
			"mask-image-radial-size": [{ "mask-radial": [{
				closest: ["side", "corner"],
				farthest: ["side", "corner"]
			}] }],
			"mask-image-radial-pos": [{ "mask-radial-at": scalePosition() }],
			"mask-image-conic-pos": [{ "mask-conic": [isNumber] }],
			"mask-image-conic-from-pos": [{ "mask-conic-from": scaleMaskImagePosition() }],
			"mask-image-conic-to-pos": [{ "mask-conic-to": scaleMaskImagePosition() }],
			"mask-image-conic-from-color": [{ "mask-conic-from": scaleColor() }],
			"mask-image-conic-to-color": [{ "mask-conic-to": scaleColor() }],
			/**
			* Mask Mode
			* @see https://tailwindcss.com/docs/mask-mode
			*/
			"mask-mode": [{ mask: [
				"alpha",
				"luminance",
				"match"
			] }],
			/**
			* Mask Origin
			* @see https://tailwindcss.com/docs/mask-origin
			*/
			"mask-origin": [{ "mask-origin": [
				"border",
				"padding",
				"content",
				"fill",
				"stroke",
				"view"
			] }],
			/**
			* Mask Position
			* @see https://tailwindcss.com/docs/mask-position
			*/
			"mask-position": [{ mask: scaleBgPosition() }],
			/**
			* Mask Repeat
			* @see https://tailwindcss.com/docs/mask-repeat
			*/
			"mask-repeat": [{ mask: scaleBgRepeat() }],
			/**
			* Mask Size
			* @see https://tailwindcss.com/docs/mask-size
			*/
			"mask-size": [{ mask: scaleBgSize() }],
			/**
			* Mask Type
			* @see https://tailwindcss.com/docs/mask-type
			*/
			"mask-type": [{ "mask-type": ["alpha", "luminance"] }],
			/**
			* Mask Image
			* @see https://tailwindcss.com/docs/mask-image
			*/
			"mask-image": [{ mask: [
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Filter
			* @see https://tailwindcss.com/docs/filter
			*/
			filter: [{ filter: [
				"",
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Blur
			* @see https://tailwindcss.com/docs/blur
			*/
			blur: [{ blur: scaleBlur() }],
			/**
			* Brightness
			* @see https://tailwindcss.com/docs/brightness
			*/
			brightness: [{ brightness: [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Contrast
			* @see https://tailwindcss.com/docs/contrast
			*/
			contrast: [{ contrast: [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Drop Shadow
			* @see https://tailwindcss.com/docs/drop-shadow
			*/
			"drop-shadow": [{ "drop-shadow": [
				"",
				"none",
				themeDropShadow,
				isArbitraryVariableShadow,
				isArbitraryShadow
			] }],
			/**
			* Drop Shadow Color
			* @see https://tailwindcss.com/docs/filter-drop-shadow#setting-the-shadow-color
			*/
			"drop-shadow-color": [{ "drop-shadow": scaleColor() }],
			/**
			* Grayscale
			* @see https://tailwindcss.com/docs/grayscale
			*/
			grayscale: [{ grayscale: [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Hue Rotate
			* @see https://tailwindcss.com/docs/hue-rotate
			*/
			"hue-rotate": [{ "hue-rotate": [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Invert
			* @see https://tailwindcss.com/docs/invert
			*/
			invert: [{ invert: [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Saturate
			* @see https://tailwindcss.com/docs/saturate
			*/
			saturate: [{ saturate: [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Sepia
			* @see https://tailwindcss.com/docs/sepia
			*/
			sepia: [{ sepia: [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Filter
			* @see https://tailwindcss.com/docs/backdrop-filter
			*/
			"backdrop-filter": [{ "backdrop-filter": [
				"",
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Blur
			* @see https://tailwindcss.com/docs/backdrop-blur
			*/
			"backdrop-blur": [{ "backdrop-blur": scaleBlur() }],
			/**
			* Backdrop Brightness
			* @see https://tailwindcss.com/docs/backdrop-brightness
			*/
			"backdrop-brightness": [{ "backdrop-brightness": [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Contrast
			* @see https://tailwindcss.com/docs/backdrop-contrast
			*/
			"backdrop-contrast": [{ "backdrop-contrast": [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Grayscale
			* @see https://tailwindcss.com/docs/backdrop-grayscale
			*/
			"backdrop-grayscale": [{ "backdrop-grayscale": [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Hue Rotate
			* @see https://tailwindcss.com/docs/backdrop-hue-rotate
			*/
			"backdrop-hue-rotate": [{ "backdrop-hue-rotate": [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Invert
			* @see https://tailwindcss.com/docs/backdrop-invert
			*/
			"backdrop-invert": [{ "backdrop-invert": [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Opacity
			* @see https://tailwindcss.com/docs/backdrop-opacity
			*/
			"backdrop-opacity": [{ "backdrop-opacity": [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Saturate
			* @see https://tailwindcss.com/docs/backdrop-saturate
			*/
			"backdrop-saturate": [{ "backdrop-saturate": [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backdrop Sepia
			* @see https://tailwindcss.com/docs/backdrop-sepia
			*/
			"backdrop-sepia": [{ "backdrop-sepia": [
				"",
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Border Collapse
			* @see https://tailwindcss.com/docs/border-collapse
			*/
			"border-collapse": [{ border: ["collapse", "separate"] }],
			/**
			* Border Spacing
			* @see https://tailwindcss.com/docs/border-spacing
			*/
			"border-spacing": [{ "border-spacing": scaleUnambiguousSpacing() }],
			/**
			* Border Spacing X
			* @see https://tailwindcss.com/docs/border-spacing
			*/
			"border-spacing-x": [{ "border-spacing-x": scaleUnambiguousSpacing() }],
			/**
			* Border Spacing Y
			* @see https://tailwindcss.com/docs/border-spacing
			*/
			"border-spacing-y": [{ "border-spacing-y": scaleUnambiguousSpacing() }],
			/**
			* Table Layout
			* @see https://tailwindcss.com/docs/table-layout
			*/
			"table-layout": [{ table: ["auto", "fixed"] }],
			/**
			* Caption Side
			* @see https://tailwindcss.com/docs/caption-side
			*/
			caption: [{ caption: ["top", "bottom"] }],
			/**
			* Transition Property
			* @see https://tailwindcss.com/docs/transition-property
			*/
			transition: [{ transition: [
				"",
				"all",
				"colors",
				"opacity",
				"shadow",
				"transform",
				"none",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Transition Behavior
			* @see https://tailwindcss.com/docs/transition-behavior
			*/
			"transition-behavior": [{ transition: ["normal", "discrete"] }],
			/**
			* Transition Duration
			* @see https://tailwindcss.com/docs/transition-duration
			*/
			duration: [{ duration: [
				isNumber,
				"initial",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Transition Timing Function
			* @see https://tailwindcss.com/docs/transition-timing-function
			*/
			ease: [{ ease: [
				"linear",
				"initial",
				themeEase,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Transition Delay
			* @see https://tailwindcss.com/docs/transition-delay
			*/
			delay: [{ delay: [
				isNumber,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Animation
			* @see https://tailwindcss.com/docs/animation
			*/
			animate: [{ animate: [
				"none",
				themeAnimate,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Backface Visibility
			* @see https://tailwindcss.com/docs/backface-visibility
			*/
			backface: [{ backface: ["hidden", "visible"] }],
			/**
			* Perspective
			* @see https://tailwindcss.com/docs/perspective
			*/
			perspective: [{ perspective: [
				themePerspective,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Perspective Origin
			* @see https://tailwindcss.com/docs/perspective-origin
			*/
			"perspective-origin": [{ "perspective-origin": scalePositionWithArbitrary() }],
			/**
			* Rotate
			* @see https://tailwindcss.com/docs/rotate
			*/
			rotate: [{ rotate: scaleRotate() }],
			/**
			* Rotate X
			* @see https://tailwindcss.com/docs/rotate
			*/
			"rotate-x": [{ "rotate-x": scaleRotate() }],
			/**
			* Rotate Y
			* @see https://tailwindcss.com/docs/rotate
			*/
			"rotate-y": [{ "rotate-y": scaleRotate() }],
			/**
			* Rotate Z
			* @see https://tailwindcss.com/docs/rotate
			*/
			"rotate-z": [{ "rotate-z": scaleRotate() }],
			/**
			* Scale
			* @see https://tailwindcss.com/docs/scale
			*/
			scale: [{ scale: scaleScale() }],
			/**
			* Scale X
			* @see https://tailwindcss.com/docs/scale
			*/
			"scale-x": [{ "scale-x": scaleScale() }],
			/**
			* Scale Y
			* @see https://tailwindcss.com/docs/scale
			*/
			"scale-y": [{ "scale-y": scaleScale() }],
			/**
			* Scale Z
			* @see https://tailwindcss.com/docs/scale
			*/
			"scale-z": [{ "scale-z": scaleScale() }],
			/**
			* Scale 3D
			* @see https://tailwindcss.com/docs/scale
			*/
			"scale-3d": ["scale-3d"],
			/**
			* Skew
			* @see https://tailwindcss.com/docs/skew
			*/
			skew: [{ skew: scaleSkew() }],
			/**
			* Skew X
			* @see https://tailwindcss.com/docs/skew
			*/
			"skew-x": [{ "skew-x": scaleSkew() }],
			/**
			* Skew Y
			* @see https://tailwindcss.com/docs/skew
			*/
			"skew-y": [{ "skew-y": scaleSkew() }],
			/**
			* Transform
			* @see https://tailwindcss.com/docs/transform
			*/
			transform: [{ transform: [
				isArbitraryVariable,
				isArbitraryValue,
				"",
				"none",
				"gpu",
				"cpu"
			] }],
			/**
			* Transform Origin
			* @see https://tailwindcss.com/docs/transform-origin
			*/
			"transform-origin": [{ origin: scalePositionWithArbitrary() }],
			/**
			* Transform Style
			* @see https://tailwindcss.com/docs/transform-style
			*/
			"transform-style": [{ transform: ["3d", "flat"] }],
			/**
			* Translate
			* @see https://tailwindcss.com/docs/translate
			*/
			translate: [{ translate: scaleTranslate() }],
			/**
			* Translate X
			* @see https://tailwindcss.com/docs/translate
			*/
			"translate-x": [{ "translate-x": scaleTranslate() }],
			/**
			* Translate Y
			* @see https://tailwindcss.com/docs/translate
			*/
			"translate-y": [{ "translate-y": scaleTranslate() }],
			/**
			* Translate Z
			* @see https://tailwindcss.com/docs/translate
			*/
			"translate-z": [{ "translate-z": scaleTranslate() }],
			/**
			* Translate None
			* @see https://tailwindcss.com/docs/translate
			*/
			"translate-none": ["translate-none"],
			/**
			* Zoom
			* @see https://tailwindcss.com/docs/zoom
			*/
			zoom: [{ zoom: [
				isInteger,
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Accent Color
			* @see https://tailwindcss.com/docs/accent-color
			*/
			accent: [{ accent: scaleColor() }],
			/**
			* Appearance
			* @see https://tailwindcss.com/docs/appearance
			*/
			appearance: [{ appearance: ["none", "auto"] }],
			/**
			* Caret Color
			* @see https://tailwindcss.com/docs/just-in-time-mode#caret-color-utilities
			*/
			"caret-color": [{ caret: scaleColor() }],
			/**
			* Color Scheme
			* @see https://tailwindcss.com/docs/color-scheme
			*/
			"color-scheme": [{ scheme: [
				"normal",
				"dark",
				"light",
				"light-dark",
				"only-dark",
				"only-light"
			] }],
			/**
			* Cursor
			* @see https://tailwindcss.com/docs/cursor
			*/
			cursor: [{ cursor: [
				"auto",
				"default",
				"pointer",
				"wait",
				"text",
				"move",
				"help",
				"not-allowed",
				"none",
				"context-menu",
				"progress",
				"cell",
				"crosshair",
				"vertical-text",
				"alias",
				"copy",
				"no-drop",
				"grab",
				"grabbing",
				"all-scroll",
				"col-resize",
				"row-resize",
				"n-resize",
				"e-resize",
				"s-resize",
				"w-resize",
				"ne-resize",
				"nw-resize",
				"se-resize",
				"sw-resize",
				"ew-resize",
				"ns-resize",
				"nesw-resize",
				"nwse-resize",
				"zoom-in",
				"zoom-out",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Field Sizing
			* @see https://tailwindcss.com/docs/field-sizing
			*/
			"field-sizing": [{ "field-sizing": ["fixed", "content"] }],
			/**
			* Pointer Events
			* @see https://tailwindcss.com/docs/pointer-events
			*/
			"pointer-events": [{ "pointer-events": ["auto", "none"] }],
			/**
			* Resize
			* @see https://tailwindcss.com/docs/resize
			*/
			resize: [{ resize: [
				"none",
				"",
				"y",
				"x"
			] }],
			/**
			* Scroll Behavior
			* @see https://tailwindcss.com/docs/scroll-behavior
			*/
			"scroll-behavior": [{ scroll: ["auto", "smooth"] }],
			/**
			* Scrollbar Thumb Color
			* @see https://tailwindcss.com/docs/scrollbar-color
			*/
			"scrollbar-thumb-color": [{ "scrollbar-thumb": scaleColor() }],
			/**
			* Scrollbar Track Color
			* @see https://tailwindcss.com/docs/scrollbar-color
			*/
			"scrollbar-track-color": [{ "scrollbar-track": scaleColor() }],
			/**
			* Scrollbar Gutter
			* @see https://tailwindcss.com/docs/scrollbar-gutter
			*/
			"scrollbar-gutter": [{ "scrollbar-gutter": [
				"auto",
				"stable",
				"both"
			] }],
			/**
			* Scrollbar Width
			* @see https://tailwindcss.com/docs/scrollbar-width
			*/
			"scrollbar-w": [{ scrollbar: [
				"auto",
				"thin",
				"none"
			] }],
			/**
			* Scroll Margin
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-m": [{ "scroll-m": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Inline
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-mx": [{ "scroll-mx": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Block
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-my": [{ "scroll-my": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Inline Start
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-ms": [{ "scroll-ms": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Inline End
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-me": [{ "scroll-me": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Block Start
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-mbs": [{ "scroll-mbs": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Block End
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-mbe": [{ "scroll-mbe": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Top
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-mt": [{ "scroll-mt": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Right
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-mr": [{ "scroll-mr": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Bottom
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-mb": [{ "scroll-mb": scaleUnambiguousSpacing() }],
			/**
			* Scroll Margin Left
			* @see https://tailwindcss.com/docs/scroll-margin
			*/
			"scroll-ml": [{ "scroll-ml": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-p": [{ "scroll-p": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Inline
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-px": [{ "scroll-px": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Block
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-py": [{ "scroll-py": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Inline Start
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-ps": [{ "scroll-ps": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Inline End
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-pe": [{ "scroll-pe": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Block Start
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-pbs": [{ "scroll-pbs": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Block End
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-pbe": [{ "scroll-pbe": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Top
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-pt": [{ "scroll-pt": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Right
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-pr": [{ "scroll-pr": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Bottom
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-pb": [{ "scroll-pb": scaleUnambiguousSpacing() }],
			/**
			* Scroll Padding Left
			* @see https://tailwindcss.com/docs/scroll-padding
			*/
			"scroll-pl": [{ "scroll-pl": scaleUnambiguousSpacing() }],
			/**
			* Scroll Snap Align
			* @see https://tailwindcss.com/docs/scroll-snap-align
			*/
			"snap-align": [{ snap: [
				"start",
				"end",
				"center",
				"align-none"
			] }],
			/**
			* Scroll Snap Stop
			* @see https://tailwindcss.com/docs/scroll-snap-stop
			*/
			"snap-stop": [{ snap: ["normal", "always"] }],
			/**
			* Scroll Snap Type
			* @see https://tailwindcss.com/docs/scroll-snap-type
			*/
			"snap-type": [{ snap: [
				"none",
				"x",
				"y",
				"both"
			] }],
			/**
			* Scroll Snap Type Strictness
			* @see https://tailwindcss.com/docs/scroll-snap-type
			*/
			"snap-strictness": [{ snap: ["mandatory", "proximity"] }],
			/**
			* Touch Action
			* @see https://tailwindcss.com/docs/touch-action
			*/
			touch: [{ touch: [
				"auto",
				"none",
				"manipulation"
			] }],
			/**
			* Touch Action X
			* @see https://tailwindcss.com/docs/touch-action
			*/
			"touch-x": [{ "touch-pan": [
				"x",
				"left",
				"right"
			] }],
			/**
			* Touch Action Y
			* @see https://tailwindcss.com/docs/touch-action
			*/
			"touch-y": [{ "touch-pan": [
				"y",
				"up",
				"down"
			] }],
			/**
			* Touch Action Pinch Zoom
			* @see https://tailwindcss.com/docs/touch-action
			*/
			"touch-pz": ["touch-pinch-zoom"],
			/**
			* User Select
			* @see https://tailwindcss.com/docs/user-select
			*/
			select: [{ select: [
				"none",
				"text",
				"all",
				"auto"
			] }],
			/**
			* Will Change
			* @see https://tailwindcss.com/docs/will-change
			*/
			"will-change": [{ "will-change": [
				"auto",
				"scroll",
				"contents",
				"transform",
				isArbitraryVariable,
				isArbitraryValue
			] }],
			/**
			* Fill
			* @see https://tailwindcss.com/docs/fill
			*/
			fill: [{ fill: ["none", ...scaleColor()] }],
			/**
			* Stroke Width
			* @see https://tailwindcss.com/docs/stroke-width
			*/
			"stroke-w": [{ stroke: [
				isNumber,
				isArbitraryVariableLength,
				isArbitraryLength,
				isArbitraryNumber
			] }],
			/**
			* Stroke
			* @see https://tailwindcss.com/docs/stroke
			*/
			stroke: [{ stroke: ["none", ...scaleColor()] }],
			/**
			* Forced Color Adjust
			* @see https://tailwindcss.com/docs/forced-color-adjust
			*/
			"forced-color-adjust": [{ "forced-color-adjust": ["auto", "none"] }]
		},
		conflictingClassGroups: {
			"container-named": ["container-type"],
			overflow: ["overflow-x", "overflow-y"],
			overscroll: ["overscroll-x", "overscroll-y"],
			inset: [
				"inset-x",
				"inset-y",
				"inset-bs",
				"inset-be",
				"start",
				"end",
				"top",
				"right",
				"bottom",
				"left"
			],
			"inset-x": ["right", "left"],
			"inset-y": ["top", "bottom"],
			flex: [
				"basis",
				"grow",
				"shrink"
			],
			gap: ["gap-x", "gap-y"],
			p: [
				"px",
				"py",
				"ps",
				"pe",
				"pbs",
				"pbe",
				"pt",
				"pr",
				"pb",
				"pl"
			],
			px: ["pr", "pl"],
			py: ["pt", "pb"],
			m: [
				"mx",
				"my",
				"ms",
				"me",
				"mbs",
				"mbe",
				"mt",
				"mr",
				"mb",
				"ml"
			],
			mx: ["mr", "ml"],
			my: ["mt", "mb"],
			size: ["w", "h"],
			"font-size": ["leading"],
			"fvn-normal": [
				"fvn-ordinal",
				"fvn-slashed-zero",
				"fvn-figure",
				"fvn-spacing",
				"fvn-fraction"
			],
			"fvn-ordinal": ["fvn-normal"],
			"fvn-slashed-zero": ["fvn-normal"],
			"fvn-figure": ["fvn-normal"],
			"fvn-spacing": ["fvn-normal"],
			"fvn-fraction": ["fvn-normal"],
			"line-clamp": ["display", "overflow"],
			rounded: [
				"rounded-s",
				"rounded-e",
				"rounded-t",
				"rounded-r",
				"rounded-b",
				"rounded-l",
				"rounded-ss",
				"rounded-se",
				"rounded-ee",
				"rounded-es",
				"rounded-tl",
				"rounded-tr",
				"rounded-br",
				"rounded-bl"
			],
			"rounded-s": ["rounded-ss", "rounded-es"],
			"rounded-e": ["rounded-se", "rounded-ee"],
			"rounded-t": ["rounded-tl", "rounded-tr"],
			"rounded-r": ["rounded-tr", "rounded-br"],
			"rounded-b": ["rounded-br", "rounded-bl"],
			"rounded-l": ["rounded-tl", "rounded-bl"],
			"border-spacing": ["border-spacing-x", "border-spacing-y"],
			"border-w": [
				"border-w-x",
				"border-w-y",
				"border-w-s",
				"border-w-e",
				"border-w-bs",
				"border-w-be",
				"border-w-t",
				"border-w-r",
				"border-w-b",
				"border-w-l"
			],
			"border-w-x": ["border-w-r", "border-w-l"],
			"border-w-y": ["border-w-t", "border-w-b"],
			"border-color": [
				"border-color-x",
				"border-color-y",
				"border-color-s",
				"border-color-e",
				"border-color-bs",
				"border-color-be",
				"border-color-t",
				"border-color-r",
				"border-color-b",
				"border-color-l"
			],
			"border-color-x": ["border-color-r", "border-color-l"],
			"border-color-y": ["border-color-t", "border-color-b"],
			translate: [
				"translate-x",
				"translate-y",
				"translate-none"
			],
			"translate-none": [
				"translate",
				"translate-x",
				"translate-y",
				"translate-z"
			],
			"scroll-m": [
				"scroll-mx",
				"scroll-my",
				"scroll-ms",
				"scroll-me",
				"scroll-mbs",
				"scroll-mbe",
				"scroll-mt",
				"scroll-mr",
				"scroll-mb",
				"scroll-ml"
			],
			"scroll-mx": ["scroll-mr", "scroll-ml"],
			"scroll-my": ["scroll-mt", "scroll-mb"],
			"scroll-p": [
				"scroll-px",
				"scroll-py",
				"scroll-ps",
				"scroll-pe",
				"scroll-pbs",
				"scroll-pbe",
				"scroll-pt",
				"scroll-pr",
				"scroll-pb",
				"scroll-pl"
			],
			"scroll-px": ["scroll-pr", "scroll-pl"],
			"scroll-py": ["scroll-pt", "scroll-pb"],
			touch: [
				"touch-x",
				"touch-y",
				"touch-pz"
			],
			"touch-x": ["touch"],
			"touch-y": ["touch"],
			"touch-pz": ["touch"]
		},
		conflictingClassGroupModifiers: { "font-size": ["leading"] },
		postfixLookupClassGroups: ["container-type"],
		orderSensitiveModifiers: [
			"*",
			"**",
			"after",
			"backdrop",
			"before",
			"details-content",
			"file",
			"first-letter",
			"first-line",
			"marker",
			"placeholder",
			"selection"
		]
	};
};
var twMerge = /*#__PURE__*/ createTailwindMerge(getDefaultConfig);
//#endregion
//#region src/lib/utils.ts
function cn(...inputs) {
	return twMerge(clsx(inputs));
}
//#endregion
//#region src/lib/rift/action-contract.ts
function isDeployableRecommendation(value) {
	if (!value || typeof value !== "object" || Array.isArray(value)) return false;
	const candidate = value;
	const support = String(candidate.support_level ?? "").toUpperCase();
	const backend = String(candidate.backend ?? "").toLowerCase();
	return support !== "UNSUPPORTED" && backend !== "" && backend !== "none" && backend !== "external";
}
function recommendationSelector(priority) {
	if (priority === "quality") return "highest_quality";
	if (priority === "speed") return "fastest";
	return "best_estimated";
}
function planRequest(recommendationRunId, selector, intent = {}) {
	if (!recommendationRunId.trim()) throw new Error("recommendation run id is required");
	const request = {
		recommendation_run_id: recommendationRunId,
		selector
	};
	if (intent.artifactId) request.artifact_id = intent.artifactId;
	if (intent.backendKind) request.backend_kind = intent.backendKind;
	if (intent.targetNodeId) request.target_node_id = intent.targetNodeId;
	if (intent.serviceName) request.service_name = intent.serviceName;
	if (intent.exposure) request.exposure = intent.exposure;
	return request;
}
function applyRequest(configPath, permissions, plan) {
	if (!configPath.trim()) throw new Error("materialized config path is required");
	const request = {
		config: configPath,
		allow_download: permissions.allowDownload,
		allow_install: permissions.allowInstall,
		allow_launch: permissions.allowLaunch,
		allow_remote: permissions.allowRemote ?? false,
		optimize: permissions.optimize ?? false,
		write_back: permissions.writeBack ?? false
	};
	if (plan?.id) request.plan_id = plan.id;
	if (plan?.hash) request.plan_hash = plan.hash;
	return request;
}
//#endregion
//#region src/lib/rift/report-mapping.ts
function object$1(value) {
	return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function numeric$1(value, fallback = 0) {
	return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
function text$1(value, fallback = "") {
	return typeof value === "string" ? value : fallback;
}
function basename$1(value) {
	return value.split(/[\\/]/).pop() ?? value;
}
function reportSummary(report) {
	const summary = object$1(report.summary);
	return Object.keys(summary).length ? summary : report;
}
function mapBenchmarkReport(entry, serviceId) {
	const item = object$1(entry);
	const path = text$1(item.path);
	if (!path.toLowerCase().includes("benchmark") || path.toLowerCase().includes("cluster")) return null;
	const reportPayload = reportSummary(item);
	const nestedSummary = object$1(reportPayload.summary);
	const summary = Object.keys(nestedSummary).length ? nestedSummary : reportPayload;
	const metrics = object$1(summary.metrics);
	const backendTimings = object$1(summary.backend_timings);
	const caseSummaries = (Array.isArray(reportPayload.cases) ? reportPayload.cases.map(object$1) : Array.isArray(item.cases) ? item.cases.map(object$1) : []).map((value) => object$1(value.summary));
	const tokensPerSec = numeric$1(summary.decode_tokens_per_second, numeric$1(summary.tokens_per_second_estimate, numeric$1(summary.median_tokens_per_second, numeric$1(metrics.tokens_per_second, numeric$1(backendTimings.predicted_per_second)))));
	if (tokensPerSec <= 0) return null;
	const firstTokenSeconds = numeric$1(summary.time_to_first_token_seconds_estimate, numeric$1(summary.median_first_token_seconds, numeric$1(metrics.first_token_seconds, numeric$1(caseSummaries[0]?.median_first_token_seconds))));
	const launchPlan = object$1(object$1(reportPayload.metadata ?? item.metadata).launch_plan);
	const created = numeric$1(item.created_unix_seconds) || numeric$1(reportPayload.created_unix_seconds) || numeric$1(summary.created_unix_seconds) || numeric$1(basename$1(path).split("-")[0]);
	return {
		id: basename$1(path),
		serviceId,
		measuredAt: (/* @__PURE__ */ new Date(created * 1e3)).toISOString(),
		tokensPerSec,
		firstTokenMs: Math.round(firstTokenSeconds * 1e3),
		concurrency: numeric$1(summary.concurrency, numeric$1(launchPlan.concurrency, 1)),
		contextTokens: numeric$1(summary.context_tokens, numeric$1(summary.prompt_tokens, numeric$1(launchPlan.context_length, 0))),
		outputTokens: numeric$1(summary.generated_tokens_estimate, numeric$1(metrics.generated_tokens, 0)),
		provenance: "live"
	};
}
//#endregion
//#region src/lib/rift/operation-state.ts
var terminalStages = {
	SUCCEEDED: "succeeded",
	FAILED: "failed",
	CANCELLED: "cancelled",
	INTERRUPTED: "interrupted"
};
function deriveOperationDisplay(input) {
	const status = input.status.trim().toUpperCase();
	const stage = input.stage?.trim() || terminalStages[status] || "running";
	const message = input.message?.trim() || input.error?.trim() || (status === "SUCCEEDED" ? "Operation completed successfully." : status === "FAILED" || status === "INTERRUPTED" || status === "CANCELLED" ? "Operation did not complete successfully." : "Operation in progress.");
	return {
		stage,
		percent: input.percent === null ? null : typeof input.percent === "number" && Number.isFinite(input.percent) ? input.percent : status === "SUCCEEDED" ? 100 : null,
		message
	};
}
//#endregion
//#region src/lib/rift/client.ts
var RiftUnavailable = class extends Error {
	endpoint;
	method;
	reason;
	detail;
	constructor(endpoint, method, reason, detail) {
		super(`RIFT ${method} ${endpoint} unavailable: ${reason}${detail ? ` - ${detail}` : ""}`);
		this.endpoint = endpoint;
		this.method = method;
		this.reason = reason;
		this.detail = detail;
		this.name = "RiftUnavailable";
	}
};
var RiftApiError = class extends Error {
	status;
	endpoint;
	body;
	constructor(status, endpoint, body) {
		const detail = typeof body === "string" ? body : body && typeof body === "object" ? String(body.detail ?? body.error ?? body.message ?? "") : "";
		super(`RIFT ${endpoint} failed: ${status}${detail ? ` - ${detail}` : ""}`);
		this.status = status;
		this.endpoint = endpoint;
		this.body = body;
		this.name = "RiftApiError";
	}
};
var DEFAULT_TIMEOUT_MS = 12e4;
function configuredRoot() {
	const configured = (typeof window !== "undefined" ? window.RIFT_CONTROL_API?.trim() : void 0) || {
		"BASE_URL": "/",
		"DEV": false,
		"MODE": "production",
		"PROD": true,
		"SSR": true,
		"TSS_DEV_SERVER": "false",
		"TSS_DEV_SSR_STYLES_BASEPATH": "/",
		"TSS_DEV_SSR_STYLES_ENABLED": "true",
		"TSS_DISABLE_CSRF_MIDDLEWARE_WARNING": "false",
		"TSS_INLINE_CSS_ENABLED": "false",
		"TSS_ROUTER_BASEPATH": "",
		"TSS_SERVER_FN_BASE": "/_serverFn/"
	}.VITE_RIFT_CONTROLLER_URL?.trim();
	if (!configured) return "/api/rift";
	const root = configured.replace(/\/+$/, "");
	if (root.endsWith("/api/rift")) return root;
	if (root.endsWith("/api/rift/v1")) return root.slice(0, -3);
	return `${root}/api/rift`;
}
function previewEnabled() {
	const env = {
		"BASE_URL": "/",
		"DEV": false,
		"MODE": "production",
		"PROD": true,
		"SSR": true,
		"TSS_DEV_SERVER": "false",
		"TSS_DEV_SSR_STYLES_BASEPATH": "/",
		"TSS_DEV_SSR_STYLES_ENABLED": "true",
		"TSS_DISABLE_CSRF_MIDDLEWARE_WARNING": "false",
		"TSS_INLINE_CSS_ENABLED": "false",
		"TSS_ROUTER_BASEPATH": "",
		"TSS_SERVER_FN_BASE": "/_serverFn/"
	};
	const configured = env.VITE_RIFT_PREVIEW_DATA;
	if (typeof configured === "string") return configured.toLowerCase() === "true";
	return env.DEV === true;
}
async function req(method, path, body, signal, timeoutMs = DEFAULT_TIMEOUT_MS) {
	const ac = new AbortController();
	const timeoutId = setTimeout(() => ac.abort(), timeoutMs);
	const combined = signal ? new AbortController() : ac;
	if (signal) {
		signal.addEventListener("abort", () => combined.abort(), { once: true });
		ac.signal.addEventListener("abort", () => combined.abort(), { once: true });
	}
	try {
		const response = await fetch(`${configuredRoot()}${path}`, {
			method,
			headers: {
				Accept: "application/json",
				...body ? { "Content-Type": "application/json" } : {}
			},
			body: body ? JSON.stringify(body) : void 0,
			signal: combined.signal,
			credentials: "include"
		});
		const payload = (response.headers.get("content-type") ?? "").includes("application/json") ? await response.json() : await response.text();
		if (!response.ok) {
			if (response.status === 404 || response.status === 501) throw new RiftUnavailable(path, method, "not-implemented");
			throw new RiftApiError(response.status, path, payload);
		}
		return payload;
	} catch (error) {
		if (error instanceof RiftApiError || error instanceof RiftUnavailable) throw error;
		if (error.name === "AbortError") throw new RiftUnavailable(path, method, "timeout");
		throw new RiftUnavailable(path, method, "controller-offline", error instanceof Error ? error.message : String(error));
	} finally {
		clearTimeout(timeoutId);
	}
}
function object(value) {
	return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function list(value) {
	return Array.isArray(value) ? value : [];
}
function text(value, fallback = "") {
	return typeof value === "string" && value ? value : fallback;
}
function numeric(value, fallback = 0) {
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : fallback;
}
function bool(value, fallback = false) {
	return typeof value === "boolean" ? value : fallback;
}
function isoFromUnix(value, fallback = Date.now()) {
	const seconds = numeric(value, fallback / 1e3);
	return (/* @__PURE__ */ new Date(seconds * 1e3)).toISOString();
}
function iso(value, fallback = Date.now()) {
	if (typeof value === "string" && value) {
		const parsed = Date.parse(value);
		if (Number.isFinite(parsed)) return new Date(parsed).toISOString();
	}
	return isoFromUnix(value, fallback);
}
function trustState(value) {
	const state = text(value, "DISCOVERED_UNTRUSTED").toUpperCase();
	if (state === "PAIRING_PENDING" || state === "ENROLLED" || state === "ACTIVE" || state === "REVOKED") return state;
	return "DISCOVERED_UNTRUSTED";
}
function mapMeshSighting(value) {
	const raw = object(value);
	return {
		sightingId: text(raw.sighting_id, text(raw.sightingId)),
		provider: text(raw.provider, "unknown"),
		endpoint: text(raw.endpoint),
		nodeHint: text(raw.node_hint, text(raw.nodeHint, "Unnamed node")),
		apiVersion: text(raw.api_version, text(raw.apiVersion, "unknown")),
		bootstrapFingerprint: text(raw.bootstrap_fingerprint, text(raw.bootstrapFingerprint)),
		observedAt: iso(raw.observed_at ?? raw.observedAt),
		expiresAt: iso(raw.expires_at ?? raw.expiresAt),
		interfaceId: text(raw.interface_id, text(raw.interfaceId)) || void 0,
		trustState: trustState(raw.trust_state ?? raw.trustState),
		metadata: object(raw.metadata)
	};
}
function mapMeshNode(value) {
	const raw = object(value);
	const state = trustState(raw.trust_state ?? raw.trustState ?? "ENROLLED");
	const routable = bool(raw.routable, state === "ACTIVE");
	return {
		nodeId: text(raw.node_id, text(raw.nodeId, text(raw.id))),
		hostname: text(raw.hostname, text(raw.node_hint, text(raw.nodeHint, "Unnamed node"))),
		endpoint: text(raw.endpoint) || void 0,
		trustState: state,
		routable,
		certificateRequired: bool(raw.certificate_required ?? raw.certificateRequired, !routable),
		healthy: bool(raw.healthy, true),
		queueDepth: numeric(raw.queue_depth, numeric(raw.queueDepth)),
		labels: Object.fromEntries(Object.entries(object(raw.labels)).map(([key, entry]) => [key, text(entry)])),
		enrolledAt: raw.enrolled_at || raw.enrolledAt ? iso(raw.enrolled_at ?? raw.enrolledAt) : void 0,
		lastSeenAt: raw.last_seen_at || raw.lastSeenAt ? iso(raw.last_seen_at ?? raw.lastSeenAt) : void 0,
		capabilities: Object.keys(object(raw.capabilities)).length ? object(raw.capabilities) : void 0
	};
}
function mapMeshLink(value) {
	const raw = object(value);
	return {
		sourceNodeId: text(raw.source_node_id, text(raw.sourceNodeId)),
		targetNodeId: text(raw.target_node_id, text(raw.targetNodeId)),
		rttP50Ms: numeric(raw.rtt_p50_ms, numeric(raw.rttP50Ms)),
		rttP95Ms: numeric(raw.rtt_p95_ms, numeric(raw.rttP95Ms)),
		jitterMs: numeric(raw.jitter_ms, numeric(raw.jitterMs)),
		lossRatio: numeric(raw.loss_ratio, numeric(raw.lossRatio)),
		uploadMbps: numeric(raw.upload_mbps, numeric(raw.uploadMbps)),
		downloadMbps: numeric(raw.download_mbps, numeric(raw.downloadMbps)),
		evidence: text(raw.evidence, "UNKNOWN")
	};
}
function mapEnrollmentChallenge(value) {
	const raw = object(value);
	const state = text(raw.state, "PAIRING_PENDING").toUpperCase();
	return {
		enrollmentId: text(raw.enrollment_id, text(raw.enrollmentId, text(raw.id))),
		sightingId: text(raw.sighting_id, text(raw.sightingId)),
		expiresAt: iso(raw.expires_at ?? raw.expiresAt),
		state: state === "APPROVED" || state === "EXPIRED" || state === "REJECTED" ? state : "PAIRING_PENDING",
		nodeHint: text(raw.node_hint, text(raw.nodeHint)) || void 0
	};
}
function mapManagedEnrollment(value) {
	const raw = object(value);
	const state = text(raw.state, "PAIRING_PENDING").toUpperCase();
	return {
		enrollmentId: text(raw.enrollment_id, text(raw.enrollmentId, text(raw.id))),
		nodeId: text(raw.node_id, text(raw.nodeId)) || void 0,
		displayName: text(raw.display_name, text(raw.displayName)) || void 0,
		endpoint: text(raw.endpoint) || void 0,
		state,
		expiresAt: raw.expires_at || raw.expiresAt ? iso(raw.expires_at ?? raw.expiresAt) : void 0,
		attempts: raw.attempts === void 0 ? void 0 : numeric(raw.attempts)
	};
}
function basename(value) {
	const normalized = value.replace(/\\/g, "/").replace(/\/+$/, "");
	return normalized.split("/").pop() || normalized;
}
function backendKind(value) {
	const kind = text(value, "external").toLowerCase();
	if (kind === "llama.cpp" || kind === "llama_cpp") return "llama.cpp";
	if (kind === "vllm") return "vllm";
	if (kind === "sglang") return "sglang";
	if (kind === "lmcache_aware") return "lmcache";
	if (kind === "tgi") return "tgi";
	if (kind === "mlc") return "mlc";
	if (kind === "ollama") return "ollama";
	return "external";
}
function serviceStatus(value, raw) {
	const observation = object(raw.observation);
	const health = object(raw.health);
	const state = text(observation.phase, text(value, "unknown")).toLowerCase();
	if (state === "healthy" || state === "ready" || state === "running") return "running";
	if (state === "starting" || state === "backoff" || state === "recovering") return "degraded";
	if (state === "stopped" || state === "not_started") return "stopped";
	if (state === "crashed" || state === "unhealthy" || health.healthy === false) return "failed";
	if (state === "planning") return "planning";
	if (state === "applying") return "applying";
	return "degraded";
}
function mapService(name, value) {
	const raw = object(value);
	const runtime = object(raw.runtime);
	const launch = object(raw.launch_plan);
	const providerDetection = object(raw.provider_detection);
	const backend = object(raw.backend);
	const serving = object(raw.serving);
	const model = object(raw.model);
	const placement = object(raw.placement);
	const endpointText = text(runtime.openai_base, text(launch.openai_base));
	let scheme = "http";
	let host = text(serving.host, text(launch.host, "127.0.0.1"));
	let port = numeric(serving.port, numeric(launch.port, 0));
	let path = "/v1";
	try {
		if (endpointText) {
			const endpoint = new URL(endpointText);
			scheme = endpoint.protocol === "https:" ? "https" : "http";
			host = endpoint.hostname;
			port = numeric(endpoint.port, scheme === "https" ? 443 : 80);
			path = endpoint.pathname || "/v1";
		}
	} catch {}
	const modelId = text(model.id, text(model.selected_file, "unconfigured-model"));
	const nodeId = text(placement.node, "local");
	const updated = numeric(raw.updated_unix_seconds, numeric(runtime.started_unix_seconds));
	return {
		id: name,
		name,
		useCase: name.toLowerCase().includes("code") ? "coding" : "chat",
		status: serviceStatus(raw.status, raw),
		artifactId: modelId,
		backendKind: backendKind(raw.backend),
		assignments: [{
			nodeId,
			gpuIndices: [0],
			reservedVramBytes: numeric(object(raw.requirements).vram_bytes)
		}],
		endpoint: {
			path,
			scheme,
			port,
			bindAddress: host,
			openaiCompatible: text(serving.api, "openai") === "openai"
		},
		createdAt: isoFromUnix(runtime.started_unix_seconds, updated * 1e3 || Date.now()),
		updatedAt: isoFromUnix(updated),
		currentRevision: text(raw.config_fingerprint, `${name}-${Math.round(updated)}`),
		provenance: "live",
		details: {
			modelPath: text(model.selected_file, modelId),
			desiredState: text(raw.desired_state, "running"),
			contextLength: numeric(serving.context_length, numeric(launch.context_length)),
			concurrency: numeric(serving.concurrency, numeric(launch.concurrency, 1)),
			pid: numeric(runtime.pid) || void 0,
			restartCount: numeric(object(raw.supervisor).restart_count),
			command: text(launch.display),
			backendVersion: text(runtime.version, text(launch.version, text(providerDetection.version, text(backend.version)))) || void 0,
			exposure: text(raw.exposure, "local"),
			model,
			serving,
			gateway: object(raw.gateway),
			launchPlan: launch
		}
	};
}
function mapDeploymentRecord(value) {
	const raw = object(value);
	const status = text(raw.status, "deleted").toLowerCase();
	return {
		deploymentId: text(raw.deployment_id, text(raw.deploymentId, "unknown")),
		serviceName: text(raw.service_name, text(raw.serviceName, "unknown")),
		displayName: text(raw.display_name, text(raw.service_name, "Saved deployment")),
		status: status === "ready" || status === "stopped" || status === "failed" ? status : "deleted",
		model: object(raw.model),
		backend: {
			kind: backendKind(object(raw.backend).kind),
			version: text(object(raw.backend).version) || void 0,
			executable: text(object(raw.backend).executable) || void 0
		},
		node: Object.keys(object(raw.node)).length ? object(raw.node) : void 0,
		endpoint: {
			apiBase: text(object(raw.endpoint).api_base, text(object(raw.endpoint).apiBase)) || void 0,
			openaiBase: text(object(raw.endpoint).openai_base, text(object(raw.endpoint).openaiBase)) || void 0,
			host: text(object(raw.endpoint).host) || void 0,
			port: numeric(object(raw.endpoint).port) || void 0,
			path: text(object(raw.endpoint).path, "/v1")
		},
		serving: object(raw.serving),
		gateway: object(raw.gateway),
		launch: object(raw.launch),
		lastKnownGood: object(raw.last_known_good),
		plan: {
			id: text(object(raw.plan).id) || void 0,
			hash: text(object(raw.plan).hash) || void 0,
			configPath: text(object(raw.plan).config_path, text(object(raw.plan).configPath)) || void 0
		},
		configSnapshotPath: text(raw.config_snapshot_path) || void 0,
		relaunchCount: numeric(raw.relaunch_count),
		createdAt: iso(raw.created_unix_seconds),
		updatedAt: iso(raw.updated_unix_seconds, numeric(raw.created_unix_seconds, Date.now() / 1e3) * 1e3),
		lastStartedAt: raw.last_started_unix_seconds ? iso(raw.last_started_unix_seconds) : void 0,
		stoppedAt: raw.stopped_unix_seconds ? iso(raw.stopped_unix_seconds) : void 0,
		deletedAt: raw.deleted_unix_seconds ? iso(raw.deleted_unix_seconds) : void 0,
		provenance: "live"
	};
}
async function listDeploymentRecords(signal) {
	return list((await req("GET", "/v2/deployment-records", void 0, signal)).records).map(mapDeploymentRecord);
}
function mapServices(payload) {
	return Object.entries(object(payload)).map(([name, service]) => mapService(name, service));
}
async function listServices(signal) {
	return mapServices(await req("GET", "/services", void 0, signal));
}
function mapTelemetrySample(value) {
	const raw = object(value);
	return {
		observedAt: iso(raw.observed_at),
		serviceName: text(raw.service_name) || void 0,
		processId: numeric(raw.process_id) || void 0,
		cpuPercent: raw.cpu_percent == null ? void 0 : numeric(raw.cpu_percent),
		processCpuPercent: raw.process_cpu_percent == null ? void 0 : numeric(raw.process_cpu_percent),
		hostRamAvailableBytes: raw.host_ram_available_bytes == null ? void 0 : numeric(raw.host_ram_available_bytes),
		hostRamPressurePercent: raw.host_ram_pressure_percent == null ? void 0 : numeric(raw.host_ram_pressure_percent),
		cpuTemperatureC: raw.cpu_temperature_c == null ? void 0 : numeric(raw.cpu_temperature_c),
		processRssBytes: raw.process_rss_bytes == null ? void 0 : numeric(raw.process_rss_bytes),
		gpuUtilizationPercent: raw.gpu_utilization_percent == null ? void 0 : numeric(raw.gpu_utilization_percent),
		gpuTemperatureC: raw.gpu_temperature_c == null ? void 0 : numeric(raw.gpu_temperature_c),
		gpuVramUsedBytes: raw.gpu_vram_used_bytes == null ? void 0 : numeric(raw.gpu_vram_used_bytes),
		gpuVramTotalBytes: raw.gpu_vram_total_bytes == null ? void 0 : numeric(raw.gpu_vram_total_bytes),
		gpuVramPressurePercent: raw.gpu_vram_pressure_percent == null ? void 0 : numeric(raw.gpu_vram_pressure_percent),
		gpuPowerWatts: raw.gpu_power_watts == null ? void 0 : numeric(raw.gpu_power_watts),
		availability: Object.fromEntries(Object.entries(object(raw.availability)).map(([key, item]) => [key, text(item)]))
	};
}
function mapResourceReport(value) {
	const raw = object(value);
	const rawCosts = object(raw.costs);
	const costNumber = (snake, camel) => {
		const value = rawCosts[snake] ?? rawCosts[camel];
		return value == null || !Number.isFinite(Number(value)) ? void 0 : Number(value);
	};
	return {
		reportId: text(raw.report_id, "unknown"),
		sessionId: text(raw.session_id, "unknown"),
		serviceName: text(raw.service_name, "unknown"),
		nodeId: text(raw.node_id, "local"),
		startedAt: iso(raw.started_at),
		stoppedAt: iso(raw.stopped_at),
		durationSeconds: numeric(raw.duration_seconds),
		sampleCount: numeric(raw.sample_count),
		metrics: object(raw.metrics),
		costs: {
			energyJoules: costNumber("energy_joules", "energyJoules"),
			electricityCost: costNumber("electricity_cost", "electricityCost"),
			computeCost: costNumber("compute_cost", "computeCost"),
			totalCost: costNumber("total_cost", "totalCost"),
			currency: typeof rawCosts.currency === "string" ? rawCosts.currency : null,
			basis: text(rawCosts.basis) || void 0
		},
		coverage: object(raw.coverage)
	};
}
async function telemetryLatest(service, signal) {
	return list((await req("GET", `/telemetry/latest${service ? `?service=${encodeURIComponent(service)}` : ""}`, void 0, signal)).samples).map((item) => {
		const raw = object(item);
		const session = object(raw.session);
		return {
			session: {
				sessionId: text(session.session_id, "unknown"),
				serviceName: text(session.service_name, "unknown"),
				nodeId: text(session.node_id, "local"),
				status: text(session.status, "running"),
				startedAt: iso(session.started_at),
				stoppedAt: session.stopped_at == null ? void 0 : iso(session.stopped_at),
				sampleCount: numeric(session.sample_count)
			},
			sample: mapTelemetrySample(raw.sample)
		};
	});
}
async function resourceReports(service, signal) {
	return list((await req("GET", `/telemetry/reports${service ? `?service=${encodeURIComponent(service)}` : ""}`, void 0, signal)).reports).map(mapResourceReport);
}
async function serviceTelemetryAccounting(service, signal) {
	return mapServiceTelemetryAccounting(await req("GET", `/v2/services/${encodeURIComponent(service)}/telemetry/accounting`, void 0, signal));
}
function mapServiceTelemetryAccounting(value) {
	const raw = object(value);
	const source = (entry) => {
		const normalized = text(entry, "unconfigured");
		return normalized === "service" || normalized === "global" ? normalized : "unconfigured";
	};
	const nullableNumber = (entry) => entry == null || !Number.isFinite(Number(entry)) ? null : Number(entry);
	return {
		apiVersion: text(raw.api_version, "2"),
		service: text(raw.service),
		configPath: text(raw.config_path) || void 0,
		electricityPricePerKwh: nullableNumber(raw.electricity_price_per_kwh),
		computeCostPerNodeHour: nullableNumber(raw.compute_cost_per_node_hour),
		electricityPriceSource: source(raw.electricity_price_source),
		computeCostSource: source(raw.compute_cost_source),
		configured: bool(raw.configured),
		currency: typeof raw.currency === "string" ? raw.currency : null,
		serviceOverrides: Object.fromEntries(Object.entries(object(raw.service_overrides)).map(([key, entry]) => [key, nullableNumber(entry)])),
		globalDefaults: Object.fromEntries(Object.entries(object(raw.global_defaults)).map(([key, entry]) => [key, nullableNumber(entry)]))
	};
}
async function updateServiceTelemetryAccounting(service, options) {
	return mapServiceTelemetryAccounting(await req("POST", `/v2/services/${encodeURIComponent(service)}/telemetry/accounting`, { accounting: {
		...options.electricityPricePerKwh !== void 0 ? { electricity_price_per_kwh: options.electricityPricePerKwh } : {},
		...options.computeCostPerNodeHour !== void 0 ? { compute_cost_per_node_hour: options.computeCostPerNodeHour } : {}
	} }));
}
async function listNodes(signal) {
	const [hardwarePayload, backendsPayload] = await Promise.all([req("GET", "/hardware", void 0, signal), req("GET", "/backends", void 0, signal)]);
	const hardware = object(hardwarePayload);
	const identity = object(hardware.identity);
	const capacity = object(hardware.capacity);
	const pressure = object(hardware.pressure);
	const storage = object(hardware.storage);
	const providers = object(backendsPayload.providers);
	const installed = Object.entries(providers).filter(([, provider]) => bool(object(object(provider).detection).available)).map(([name, provider]) => {
		return `${name}@${text(object(object(provider).detection).version, "detected")}`;
	});
	const totalVram = numeric(hardware.total_vram_bytes, numeric(capacity.vram_bytes));
	const freeVram = numeric(hardware.free_vram_bytes, numeric(pressure.vram_free_bytes, totalVram));
	const totalRam = numeric(hardware.total_host_ram_bytes, numeric(capacity.host_ram_bytes));
	const freeRam = numeric(hardware.free_host_ram_bytes, numeric(pressure.host_ram_free_bytes, totalRam));
	const diskTotal = numeric(storage.total_bytes, numeric(capacity.disk_total_bytes));
	const diskFree = numeric(storage.free_bytes, numeric(pressure.disk_free_bytes));
	const hasCuda = bool(hardware.cuda_available);
	return [{
		id: "local",
		hostname: text(identity.hostname, "local"),
		role: "controller+agent",
		status: "ready",
		address: "127.0.0.1",
		os: text(identity.os, "unknown"),
		arch: text(identity.architecture, "unknown"),
		ramBytes: totalRam,
		ramFreeBytes: freeRam,
		diskBytes: diskTotal,
		diskFreeBytes: diskFree,
		accelerators: hasCuda ? [{
			index: numeric(hardware.cuda_device_id),
			vendor: "nvidia",
			name: text(hardware.device_name, text(identity.gpu, "CUDA GPU")),
			vramBytes: totalVram,
			vramFreeBytes: freeVram,
			computeCapability: `${numeric(hardware.compute_capability_major)}.${numeric(hardware.compute_capability_minor)}`
		}] : [],
		backends: installed,
		labels: {
			source: "local-controller",
			profile: text(hardware.profile_kind, "observed")
		},
		enrolledAt: isoFromUnix(hardware.created_unix_seconds),
		lastHeartbeatAt: (/* @__PURE__ */ new Date()).toISOString(),
		version: "legacy-control-api",
		provenance: "live",
		telemetry: {
			cpuModel: text(identity.cpu_model, "unknown"),
			logicalCpuCount: numeric(identity.logical_cpu_count, numeric(capacity.logical_cpu_count)),
			diskReadMiBs: numeric(object(object(hardware.calibration).result).disk ? object(object(object(hardware.calibration).result).disk).read_mib_s : void 0),
			temperatureC: numeric(object(hardware.power_thermal).temperature_c) || void 0,
			powerDrawW: numeric(object(hardware.power_thermal).power_draw_w) || void 0,
			gpuUtilizationPercent: numeric(object(hardware.power_thermal).gpu_utilization_percent) || void 0
		}
	}];
}
async function listIncidents(signal) {
	const [incidentPayload, services] = await Promise.all([req("GET", "/incidents", void 0, signal), listServices(signal)]);
	const history = list(object(incidentPayload).incidents).map((entry) => {
		const raw = object(entry);
		const action = text(raw.action, "detected");
		const service = text(raw.service, "unknown");
		return {
			id: text(raw.incident_id, `${service}-${numeric(raw.created_unix_seconds)}`),
			severity: action === "detected" ? "warning" : "info",
			status: "resolved",
			title: action === "restarted" ? `${service} automatically restarted` : `${service} failure detected`,
			detail: text(raw.reason, `RIFT recorded a ${action} event for ${service}.`),
			serviceId: service,
			openedAt: isoFromUnix(raw.created_unix_seconds),
			resolvedAt: isoFromUnix(raw.created_unix_seconds),
			recovery: {
				action: action === "restarted" ? "service restarted by supervisor" : action,
				automatic: action === "restarted"
			},
			provenance: "live"
		};
	});
	return [...services.filter((service) => service.status === "failed" || service.status === "degraded").map((service) => ({
		id: `active-${service.id}`,
		severity: service.status === "failed" ? "critical" : "warning",
		status: "open",
		title: `${service.name} is ${service.status}`,
		detail: `The latest controller observation reports the ${service.backendKind} service as ${service.status}.`,
		serviceId: service.id,
		openedAt: service.updatedAt,
		recovery: {
			action: "Run RIFT monitor or recover after reviewing logs.",
			automatic: false
		},
		provenance: "derived-live"
	})), ...history];
}
async function listBenchmarks(serviceId, signal) {
	return list((await req("GET", "/reports", void 0, signal)).reports).map((entry) => mapBenchmarkReport(entry, serviceId)).filter((item) => item !== null).sort((a, b) => b.measuredAt.localeCompare(a.measuredAt));
}
async function listRevisions(serviceId, signal) {
	const state = await req("GET", "/state", void 0, signal);
	const service = object(object(state.services)[serviceId]);
	if (!Object.keys(service).length) return [];
	const updated = numeric(service.updated_unix_seconds, numeric(object(service.runtime).started_unix_seconds));
	const fingerprint = text(state.config_fingerprint, `${serviceId}-${Math.round(updated)}`);
	const revisions = [{
		id: `current-${fingerprint.slice(0, 12)}`,
		serviceId,
		planHash: fingerprint,
		createdAt: isoFromUnix(updated),
		appliedBy: "RIFT controller",
		notes: "Current live controller state",
		provenance: "derived-live"
	}];
	for (const [index, tuning] of list(service.tuning_history).entries()) {
		const item = object(tuning);
		revisions.push({
			id: `tuning-${index + 1}`,
			serviceId,
			planHash: `tuning-${numeric(item.created_unix_seconds)}`,
			createdAt: isoFromUnix(item.created_unix_seconds),
			appliedBy: "RIFT auto-tuner",
			notes: `Winning configuration score ${numeric(item.selection_score).toFixed(2)}`,
			provenance: "derived-live"
		});
	}
	return revisions;
}
function mapRecommendation(value, index, runId) {
	const raw = object(value);
	const scores = object(raw.scores);
	const repo = text(raw.repo_id, `candidate-${index + 1}`);
	const format = text(raw.format, "gguf");
	const artifactSelection = object(raw.artifact_selection);
	const artifactMetadata = object(artifactSelection.metadata);
	const artifactId = text(artifactSelection.artifact_id, text(raw.artifact_id, text(raw.selected_artifact_id, repo)));
	const selectedBytes = numeric(raw.selected_download_bytes);
	const estimatedBytes = selectedBytes > 0 ? selectedBytes : Math.max(numeric(raw.estimated_download_bytes), numeric(artifactSelection.total_bytes), numeric(artifactMetadata.total_download_bytes));
	const source = text(raw.source, "huggingface");
	const backend = backendKind(raw.backend);
	return {
		id: `recommendation-${index + 1}-${repo.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`,
		recommendationRunId: runId || text(raw.recommendation_run_id) || void 0,
		priority: index === 0 ? "recommended" : index === 1 ? "quality" : "speed",
		artifact: {
			id: artifactId,
			displayName: basename(repo),
			family: text(raw.model_type, basename(repo)),
			parameters: numeric(raw.parameters_b) ? `${numeric(raw.parameters_b).toFixed(1)}B` : "unknown",
			source,
			repo,
			format,
			quantization: format === "gguf" ? "q4_k_m" : format === "awq" ? "awq" : format === "gptq" ? "gptq" : "none",
			sizeBytes: estimatedBytes,
			license: text(raw.license, "unknown"),
			trust: bool(raw.gated) ? "unknown" : "community",
			provenance: "live"
		},
		backend: {
			kind: backend,
			version: "controller-selected",
			supports: {
				formats: [format],
				accelerators: ["nvidia", "cpu"]
			}
		},
		targetNode: "local",
		rationale: list(raw.evidence).map(String).join(" ") || "Selected by RIFT hardware-aware ranking.",
		quality: {
			score: Math.round(100 * numeric(scores.quality_proxy, numeric(raw.final_score))),
			confidence: numeric(raw.confidence) >= .75 ? "high" : numeric(raw.confidence) >= .5 ? "medium" : "low",
			evidence: `RIFT quality proxy ${numeric(scores.quality_proxy).toFixed(2)}; hardware fit ${numeric(scores.hardware_fit).toFixed(2)}.`
		},
		performance: {},
		resources: {
			vramBytes: Math.min(estimatedBytes, 8 * 1024 ** 3),
			ramBytes: Math.round(estimatedBytes * .2),
			diskBytes: estimatedBytes,
			kvCacheBytes: Math.min(1024 ** 3, Math.round(estimatedBytes * .1))
		},
		compromises: list(raw.warnings).map(String),
		warnings: list(raw.warnings).map(String),
		provenance: "live"
	};
}
async function recommend(input) {
	return (await recommendDetailed(input)).recommendations;
}
async function latestCachedRecommendation(task) {
	try {
		const index = await req("GET", "/v2/recommendation-runs");
		for (const entry of list(index.runs)) {
			const summary = object(entry);
			if (text(summary.task, task) !== task) continue;
			const runId = text(summary.run_id);
			if (!runId) continue;
			try {
				const run = await req("GET", `/v2/recommendation-runs/${encodeURIComponent(runId)}`);
				if (list(run.recommendations).some(isDeployableRecommendation)) return run;
			} catch {}
		}
	} catch {}
	return null;
}
async function recommendDetailed(input) {
	if (input.source === "local") return mapRecommendationSearchResult(await req("POST", "/recommend", {
		task: input.useCase === "coding" ? "coding" : "chat",
		source: "local",
		local_path: input.localPath,
		models_dir: input.localPath,
		top: 10
	}), input.useCase === "coding" ? "coding" : "chat");
	if (input.source !== "huggingface" && input.source !== "catalog") throw new RiftUnavailable("/recommend", "POST", "not-implemented", "The current controller recommendation endpoint searches Hugging Face and its cache.");
	return mapRecommendationSearchResult(await req("POST", "/recommend", {
		task: input.useCase === "coding" ? "coding" : "chat",
		top: 10,
		candidate_limit: 200,
		max_download_gb: 12,
		formats: [
			"gguf",
			"gptq",
			"awq",
			"safetensors"
		],
		include_gated: false,
		model_ref: input.modelRef,
		endpoint: input.endpointUrl
	}), input.useCase === "coding" ? "coding" : "chat");
}
async function mapRecommendationSearchResult(payload, task) {
	const runId = text(payload.recommendation_run_id, text(payload.run_id));
	const liveRecommendations = list(payload.recommendations).filter(isDeployableRecommendation).map((value, index) => mapRecommendation(value, index, runId));
	const queryArmErrors = list(payload.query_arms).map((value) => object(value)).filter((arm) => text(arm.status).toLowerCase() === "error").map((arm) => `${text(arm.name, "Hub query")}: ${text(arm.error, "request failed")}`);
	const answer = object(payload.answer);
	const counts = object(payload.candidate_counts);
	const base = {
		headline: text(answer.headline),
		detail: text(answer.detail, text(answer.summary)),
		queryArmErrors,
		candidateCounts: {
			raw: numeric(counts.raw),
			afterFilters: numeric(counts.after_filters),
			enriched: numeric(counts.enriched),
			returned: numeric(counts.returned)
		}
	};
	if (liveRecommendations.length > 0) return {
		recommendations: liveRecommendations,
		stale: false,
		...base
	};
	const cached = await latestCachedRecommendation(task);
	if (cached) return {
		recommendations: list(cached.recommendations).filter(isDeployableRecommendation).map((value, index) => mapRecommendation(value, index, text(cached.recommendation_run_id, text(cached.run_id)))),
		stale: true,
		staleCreatedAt: isoFromUnix(cached.created_unix_seconds),
		headline: "Showing the last successful shortlist",
		detail: "Live Hub search is unavailable; cached candidates are labelled for review.",
		queryArmErrors,
		candidateCounts: base.candidateCounts
	};
	return {
		recommendations: [],
		stale: false,
		...base,
		detail: queryArmErrors.length > 0 ? text(base.detail, "Live model search failed and no deployable cached shortlist is available.") : "Live search returned no deployable model/backend pair for this hardware."
	};
}
async function fleetHealth(signal) {
	const [services, hardware, incidents] = await Promise.all([
		listServices(signal),
		req("GET", "/hardware", void 0, signal),
		listIncidents(signal)
	]);
	const capacity = object(hardware.capacity);
	const pressure = object(hardware.pressure);
	const vramTotal = numeric(hardware.total_vram_bytes, numeric(capacity.vram_bytes));
	const vramFree = numeric(hardware.free_vram_bytes, numeric(pressure.vram_free_bytes));
	const ramTotal = numeric(hardware.total_host_ram_bytes, numeric(capacity.host_ram_bytes));
	const ramFree = numeric(hardware.free_host_ram_bytes, numeric(pressure.host_ram_free_bytes));
	return {
		nodesTotal: 1,
		nodesReady: 1,
		servicesTotal: services.length,
		servicesRunning: services.filter((service) => service.status === "running").length,
		incidentsOpen: incidents.filter((incident) => incident.status !== "resolved").length,
		capacity: {
			vramUsedBytes: Math.max(0, vramTotal - vramFree),
			vramTotalBytes: vramTotal,
			ramUsedBytes: Math.max(0, ramTotal - ramFree),
			ramTotalBytes: ramTotal
		},
		controllerVersion: "legacy compatibility API",
		controllerBind: configuredRoot(),
		updatedAt: (/* @__PURE__ */ new Date()).toISOString(),
		provenance: "live"
	};
}
function mapControllerPlan(raw) {
	const created = numeric(raw.created_unix_seconds);
	const services = object(raw.services);
	const serviceId = Object.keys(services)[0] ?? "chat";
	const service = object(services[serviceId]);
	const launch = object(service.launch_plan);
	const endpointUrl = text(launch.openai_base, text(launch.api_base, text(object(service.runtime).api_base)));
	const actions = list(raw.actions).map((entry, index) => {
		const item = object(entry);
		const kind = text(item.kind, "configure");
		const group = [
			"install",
			"download",
			"configure",
			"place",
			"launch",
			"expose",
			"benchmark",
			"recover"
		].includes(kind) ? kind : "configure";
		const actionLaunch = object(item.launch_plan);
		const requiredBytes = numeric(item.required_bytes, numeric(item.size_bytes));
		return {
			id: `${group}-${index + 1}`,
			group,
			summary: text(item.message, `${group} ${text(item.service, serviceId)}`),
			nodeId: text(item.node, text(object(service.placement).node, "local")),
			artifact: requiredBytes > 0 || text(item.selected_file) ? {
				sizeBytes: requiredBytes || void 0,
				source: text(item.selected_file) || void 0
			} : void 0,
			reserves: numeric(item.required_vram_bytes) || numeric(item.required_ram_bytes) ? {
				vramBytes: numeric(item.required_vram_bytes) || void 0,
				ramBytes: numeric(item.required_ram_bytes) || void 0
			} : void 0,
			ports: numeric(actionLaunch.port) ? [numeric(actionLaunch.port)] : void 0,
			risk: kind === "error" || group === "launch" || group === "install" ? "medium" : "low",
			reversible: group !== "download"
		};
	});
	const hash = text(raw.fingerprint, text(raw.config_fingerprint, text(raw.plan_hash, `legacy-${created}`)));
	const affectedNodes = list(raw.nodes).map((node) => text(object(node).name, text(object(node).host))).filter(Boolean);
	return {
		id: text(raw.plan_id, `plan-${text(raw.recommendation_run_id, "latest")}`),
		hash: text(raw.plan_hash, hash),
		serviceId,
		actions,
		affectedNodes: affectedNodes.length ? affectedNodes : [text(object(service.placement).node, "local")],
		expectedDowntimeMs: actions.some((action) => action.group === "launch") ? 3e4 : 0,
		rollback: {
			supported: true,
			description: "RIFT retains the last known good launch plan for supervised recovery."
		},
		createdAt: isoFromUnix(created),
		expiresAt: (/* @__PURE__ */ new Date((created || Date.now() / 1e3) * 1e3 + 24 * 3600 * 1e3)).toISOString(),
		configPath: text(raw.materialized_config, text(raw.config_path)) || void 0,
		endpointUrl: endpointUrl || void 0,
		provenance: "derived-live",
		previewOnly: false
	};
}
function mapOperation(raw, planId, planHash) {
	const result = object(raw.result);
	const resultPlan = object(result.plan);
	const status = text(raw.status, "RUNNING").toUpperCase();
	const stage = text(raw.stage, "queued");
	const phase = [
		"queued",
		"preparing",
		"executing",
		"installing",
		"downloading",
		"configuring",
		"placing",
		"launching",
		"exposing",
		"benchmarking",
		"succeeded",
		"failed",
		"cancelled",
		"interrupted",
		"rolled_back"
	].includes(stage) ? stage : status === "SUCCEEDED" ? "succeeded" : status === "FAILED" ? "failed" : status === "CANCELLED" ? "cancelled" : status === "INTERRUPTED" ? "interrupted" : "executing";
	return {
		planId: text(resultPlan.plan_id, planId),
		planHash: text(resultPlan.plan_hash, planHash),
		operationId: text(raw.operation_id),
		status,
		phase,
		percent: raw.percent === null ? null : numeric(raw.percent, 0),
		message: text(raw.message, text(raw.error, "Operation in progress")),
		startedAt: iso(raw.created_unix_seconds),
		updatedAt: iso(raw.updated_unix_seconds, numeric(raw.created_unix_seconds, Date.now() / 1e3) * 1e3),
		error: text(raw.error) || void 0,
		result: Object.keys(result).length ? result : void 0
	};
}
function mapEvaluationCase(value) {
	const raw = object(value);
	const status = text(raw.status, "error").toLowerCase();
	return {
		caseId: text(raw.case_id, "unknown"),
		status: status === "pass" || status === "fail" || status === "not_assessed" || status === "error" ? status : "error",
		criteria: text(raw.criteria, "explicit deterministic criterion"),
		detail: text(raw.detail, "No detail was provided."),
		elapsedSeconds: raw.elapsed_seconds === null || raw.elapsed_seconds === void 0 ? void 0 : numeric(raw.elapsed_seconds),
		response: typeof raw.response === "string" ? raw.response : void 0,
		judge: Object.keys(object(raw.judge)).length ? {
			status: text(object(raw.judge).status, "not_assessed") === "assessed" || text(object(raw.judge).status) === "error" ? text(object(raw.judge).status) : "not_assessed",
			score: object(raw.judge).score === null || object(raw.judge).score === void 0 ? null : numeric(object(raw.judge).score),
			detail: text(object(raw.judge).detail) || null
		} : void 0
	};
}
function mapEvaluation(value) {
	const raw = object(value);
	const suite = object(raw.suite);
	const status = text(raw.status, "not_run").toLowerCase();
	return {
		runId: text(raw.run_id, "unknown"),
		service: text(raw.service, "unknown"),
		status: status === "running" || status === "completed" || status === "deadline" || status === "not_run" ? status : "not_run",
		suite: {
			id: text(suite.id, "unknown"),
			version: text(suite.version, "unknown"),
			cases: list(suite.cases)
		},
		summary: Object.fromEntries(Object.entries(object(raw.summary)).map(([key, entry]) => [key, numeric(entry)])),
		cases: list(raw.cases).map(mapEvaluationCase),
		available: bool(raw.available, true),
		required: bool(raw.required, false),
		reportPath: text(raw.report_path) || void 0,
		modelRevision: object(raw.model_revision),
		configuration: object(raw.configuration),
		assessment: text(raw.assessment) || void 0,
		provenance: "live"
	};
}
function mapOperationRecord(value) {
	const raw = object(value);
	const rawStatus = text(raw.status, "RUNNING").toUpperCase();
	const status = [
		"RUNNING",
		"SUCCEEDED",
		"FAILED",
		"CANCELLED",
		"INTERRUPTED"
	].includes(rawStatus) ? rawStatus : "FAILED";
	const result = object(raw.result);
	const display = deriveOperationDisplay({
		status,
		stage: text(raw.stage) || void 0,
		percent: raw.percent === null ? null : raw.percent === void 0 ? void 0 : numeric(raw.percent, NaN),
		message: text(raw.message) || void 0,
		error: text(raw.error) || void 0
	});
	return {
		operationId: text(raw.operation_id, "unknown"),
		requestId: text(raw.request_id, "unknown"),
		action: text(raw.action, "unknown"),
		status,
		stage: display.stage,
		message: display.message,
		percent: display.percent,
		createdAt: iso(raw.created_unix_seconds),
		updatedAt: iso(raw.updated_unix_seconds, numeric(raw.created_unix_seconds, Date.now() / 1e3) * 1e3),
		completedAt: raw.completed_unix_seconds ? iso(raw.completed_unix_seconds) : void 0,
		error: text(raw.error) || void 0,
		details: Object.keys(object(raw.details)).length ? object(raw.details) : void 0,
		result: Object.keys(result).length ? result : void 0
	};
}
function mapTuningOpportunity(value) {
	const raw = object(value);
	return {
		id: text(raw.id, "opportunity"),
		kind: text(raw.kind, "unknown"),
		status: "recommendation_only",
		tested: false,
		title: text(raw.title, "Further improvement opportunity"),
		warning: text(raw.warning, "This option is recommendation-only and was not selected by autonomous tuning."),
		profile: text(raw.profile),
		lockedValue: raw.locked_value,
		lockedValues: object(raw.locked_values)
	};
}
function mapTuningRun(value) {
	const raw = object(value);
	const profile = text(raw.profile, "speed").toLowerCase();
	const target = raw.target && typeof raw.target === "object" ? object(raw.target) : null;
	const accuracy = raw.accuracy && typeof raw.accuracy === "object" ? object(raw.accuracy) : null;
	return {
		runId: text(raw.run_id, text(raw.runId, "unknown")),
		service: text(raw.service, "unknown"),
		profile: profile === "cost" ? "cost" : "speed",
		backend: text(raw.backend, "llama.cpp"),
		status: text(raw.status, "UNKNOWN"),
		outcome: text(raw.outcome) ? text(raw.outcome) : void 0,
		applied: bool(raw.applied),
		createdAt: iso(raw.created ?? raw.created_unix_seconds),
		updatedAt: raw.updated || raw.updated_unix_seconds ? iso(raw.updated ?? raw.updated_unix_seconds) : void 0,
		baseline: object(raw.baseline),
		winner: raw.winner && typeof raw.winner === "object" ? object(raw.winner) : null,
		winnerLaunchPlan: object(raw.winner_launch_plan),
		selection: object(raw.selection),
		precisionLocks: object(raw.precision_locks),
		candidates: list(raw.candidates).map((item) => object(item)),
		opportunities: list(raw.opportunities).map(mapTuningOpportunity),
		decision: text(raw.decision) || void 0,
		reason: text(raw.reason) || void 0,
		reportPath: text(raw.report_path) || void 0,
		operationId: text(raw.operation_id) || void 0,
		error: text(raw.error) || void 0,
		events: list(raw.events).map((event) => {
			const item = object(event);
			return {
				eventId: text(item.event_id) || void 0,
				stage: text(item.stage, "update"),
				message: text(item.message, "Tuning update"),
				percent: typeof item.percent === "number" ? item.percent : null,
				createdAt: item.created ? iso(item.created) : void 0,
				details: object(item.details)
			};
		}),
		target: target ? {
			value: typeof target.value === "number" ? target.value : void 0,
			reached: typeof target.reached === "boolean" ? target.reached : void 0,
			confidenceLowerBound: typeof target.confidence_lower_bound === "number" ? target.confidence_lower_bound : null,
			reason: text(target.reason) || void 0
		} : void 0,
		accuracy: accuracy ? {
			passed: typeof accuracy.passed === "boolean" ? accuracy.passed : void 0,
			aggregateScore: typeof accuracy.aggregate_score === "number" ? accuracy.aggregate_score : null,
			worstCaseScore: typeof accuracy.worst_case_score === "number" ? accuracy.worst_case_score : null,
			tolerance: typeof accuracy.tolerance === "number" ? accuracy.tolerance : void 0,
			caseTolerance: typeof accuracy.case_tolerance === "number" ? accuracy.case_tolerance : void 0
		} : void 0,
		kvPrecisionSearch: typeof raw.kv_precision_search === "boolean" ? raw.kv_precision_search : void 0,
		rejected: list(raw.rejected).map((item) => {
			const value = object(item);
			return {
				candidate: object(value.candidate),
				rejectionReason: text(value.rejection_reason) || void 0,
				reason: text(value.reason) || void 0
			};
		}),
		applyState: raw.apply_state && typeof raw.apply_state === "object" ? object(raw.apply_state) : void 0
	};
}
async function waitForOperation(operationId) {
	const deadline = Date.now() + 15 * 6e4;
	while (Date.now() < deadline) {
		const payload = await req("GET", `/v2/operations/${encodeURIComponent(operationId)}`);
		const status = text(payload.status, "RUNNING").toUpperCase();
		if (status !== "RUNNING") {
			if (status !== "SUCCEEDED") throw new RiftApiError(409, `/v2/operations/${encodeURIComponent(operationId)}`, payload);
			return object(payload.result);
		}
		await new Promise((resolve) => window.setTimeout(resolve, 1e3));
	}
	throw new RiftUnavailable(`/v2/operations/${encodeURIComponent(operationId)}`, "GET", "timeout", "operation did not finish within 15 minutes");
}
async function resolveOperation(payload) {
	const operationId = text(payload.operation_id);
	return operationId ? waitForOperation(operationId) : payload;
}
async function resolveDeploymentAction(payload, service) {
	const resolved = await resolveOperation(payload);
	return mapOperation({
		status: "SUCCEEDED",
		stage: "succeeded",
		percent: 100,
		message: text(resolved.reason, "Deployment action completed."),
		result: resolved
	}, service, text(payload.plan_hash, "unknown"));
}
async function currentPlan(signal) {
	const raw = await req("GET", "/plan", void 0, signal);
	if (raw.available === false) throw new RiftUnavailable("/plan", "GET", "not-implemented", text(raw.reason));
	return mapControllerPlan(raw);
}
var rift = {
	isConfigured: () => true,
	connectionInfo: () => ({
		root: configuredRoot(),
		mode: "legacy-live",
		previewEnabled: previewEnabled()
	}),
	health: fleetHealth,
	listNodes,
	getNode: async (id, signal) => {
		const node = (await listNodes(signal)).find((item) => item.id === id);
		if (!node) throw new RiftApiError(404, `/nodes/${id}`, { error: "node not found" });
		return node;
	},
	createEnrollmentToken: async (_ttlSeconds = 900) => {
		throw new RiftUnavailable("/enrollment-tokens", "POST", "not-implemented", "Agent enrollment is part of the target controller-agent protocol.");
	},
	drainNode: async () => {
		throw new RiftUnavailable("/nodes/actions", "POST", "not-implemented");
	},
	listMeshSightings: async (signal) => {
		return list((await req("GET", "/v2/mesh/sightings", void 0, signal)).sightings).map(mapMeshSighting);
	},
	discoverMesh: async (providers, signal) => {
		return list((await req("POST", "/v2/mesh/discover", providers?.length ? { providers } : {}, signal)).sightings).map(mapMeshSighting);
	},
	listMeshNodes: async (signal) => {
		return list((await req("GET", "/v2/mesh/nodes", void 0, signal)).nodes).map(mapMeshNode);
	},
	getMeshTopology: async (signal) => {
		const payload = await req("GET", "/v2/mesh/topology", void 0, signal);
		return {
			nodes: list(payload.nodes).map(mapMeshNode),
			links: list(payload.links).map(mapMeshLink),
			evidence: text(payload.evidence, "UNKNOWN")
		};
	},
	beginMeshEnrollment: async (sightingId, ttlSeconds = 120, signal) => mapEnrollmentChallenge(await req("POST", "/v2/mesh/enrollments", {
		sighting_id: sightingId,
		ttl_seconds: ttlSeconds
	}, signal)),
	approveMeshEnrollment: async (enrollmentId, pairingCode, signal) => {
		const payload = await req("POST", `/v2/mesh/enrollments/${encodeURIComponent(enrollmentId)}/approve`, { pairing_code: pairingCode }, signal);
		const enrollment = object(payload.enrollment);
		const state = text(enrollment.state, "APPROVED").toUpperCase();
		return {
			node: mapMeshNode(payload.node),
			enrollment: {
				enrollmentId: text(enrollment.enrollment_id, text(enrollment.enrollmentId, enrollmentId)),
				sightingId: text(enrollment.sighting_id, text(enrollment.sightingId)),
				state: state === "PAIRING_PENDING" || state === "EXPIRED" || state === "REJECTED" ? state : "APPROVED",
				approvedAt: enrollment.approved_at || enrollment.approvedAt ? iso(enrollment.approved_at ?? enrollment.approvedAt) : void 0
			}
		};
	},
	openManagedEnrollmentWindow: async (ttlSeconds = 600) => {
		const payload = await req("POST", "/v2/mesh/enrollment-window", { ttl_seconds: ttlSeconds });
		return {
			controllerId: text(payload.controller_id, "unknown"),
			open: bool(payload.open),
			expiresAt: payload.expires_at ? iso(payload.expires_at) : void 0,
			pendingCount: numeric(payload.pending_count),
			bootstrap: object(payload.bootstrap)
		};
	},
	getManagedEnrollmentWindow: async () => {
		const payload = await req("GET", "/v2/mesh/enrollment-window");
		return {
			controllerId: text(payload.controller_id, "unknown"),
			open: bool(payload.open),
			expiresAt: payload.expires_at ? iso(payload.expires_at) : void 0,
			pendingCount: numeric(payload.pending_count)
		};
	},
	listManagedEnrollments: async () => {
		return list((await req("GET", "/v2/mesh/enrollments")).enrollments).map(mapManagedEnrollment);
	},
	approveManagedEnrollment: async (enrollmentId, pairingCode) => mapManagedEnrollment(object(await req("POST", `/v2/mesh/enrollments/${encodeURIComponent(enrollmentId)}/approve`, { pairing_code: pairingCode })).enrollment),
	cancelManagedEnrollment: async (enrollmentId) => mapManagedEnrollment(await req("POST", `/v2/mesh/enrollments/${encodeURIComponent(enrollmentId)}/cancel`, {})),
	listServices,
	telemetryLatest,
	resourceReports,
	serviceTelemetryAccounting,
	updateServiceTelemetryAccounting,
	listDeploymentRecords,
	getService: async (id, signal) => {
		const service = (await listServices(signal)).find((item) => item.id === id);
		if (!service) throw new RiftApiError(404, `/services/${id}`, { error: "service not found" });
		return service;
	},
	listRevisions,
	listBenchmarks,
	recommend,
	recommendDetailed,
	createPlan: async (input) => {
		if (!input.recommendationRunId) throw new RiftUnavailable("/v2/plans", "POST", "not-implemented", "The live recommendation run is missing; run model discovery again.");
		return mapControllerPlan(await req("POST", "/v2/plans", planRequest(input.recommendationRunId, input.selector ?? recommendationSelector("recommended"), {
			artifactId: input.artifactId,
			backendKind: input.backendKind,
			targetNodeId: input.targetNodeId,
			serviceName: input.serviceName,
			exposure: input.exposure
		})));
	},
	getPlan: async (id, signal) => {
		return mapControllerPlan(await req("GET", `/v2/plans/${encodeURIComponent(id)}`, void 0, signal));
	},
	applyPlan: async (id, planHash, options) => {
		const payload = await req("POST", `/v2/plans/${encodeURIComponent(id)}/apply`, applyRequest(options.configPath, options, {
			id,
			hash: planHash
		}), void 0, 1800 * 1e3);
		if (payload.applied === false && !payload.operation_id) throw new RiftApiError(409, `/v2/plans/${encodeURIComponent(id)}/apply`, payload);
		return mapOperation(payload, id, planHash);
	},
	getOperation: async (operationId, planId, planHash, signal) => {
		return mapOperation(await req("GET", `/v2/operations/${encodeURIComponent(operationId)}`, void 0, signal), planId, planHash);
	},
	listOperations: async (signal) => {
		return list((await req("GET", "/v2/operations", void 0, signal)).operations).map(mapOperationRecord);
	},
	tuningProfiles: async (signal) => req("GET", "/v2/tuning/profiles", void 0, signal),
	listTuningRuns: async (options = {}, signal) => {
		const params = new URLSearchParams();
		if (options.service) params.set("service", options.service);
		if (options.profile) params.set("profile", options.profile);
		if (options.limit) params.set("limit", String(options.limit));
		return list((await req("GET", `/v2/tuning/runs${params.toString() ? `?${params.toString()}` : ""}`, void 0, signal)).runs).map(mapTuningRun);
	},
	getTuningRun: async (runId, signal) => mapTuningRun(await req("GET", `/v2/tuning/runs/${encodeURIComponent(runId)}`, void 0, signal)),
	startTuning: async (service, profile, options) => req("POST", "/v2/tuning/runs", {
		service,
		profile,
		allow_restart: options.allowRestart,
		no_apply: options.noApply ?? false,
		candidate_limit: options.candidateLimit ?? 24,
		warmup_runs: options.warmupRuns ?? 1,
		repeats: options.repeats ?? 3,
		budget_seconds: options.budgetSeconds,
		dry_run: options.dryRun ?? false,
		startup_timeout_seconds: options.startupTimeoutSeconds ?? 180,
		prompt: options.prompt,
		max_tokens: options.maxTokens ?? 32,
		target_tokens_per_second: options.targetTokensPerSecond ?? 100,
		accuracy_tolerance: options.accuracyTolerance ?? .05,
		accuracy_case_tolerance: options.accuracyCaseTolerance ?? .15,
		retain_accuracy_responses: options.retainAccuracyResponses ?? false,
		kv_precision_search: options.kvPrecisionSearch ?? true,
		ngram_speculation: options.ngramSpeculation
	}),
	cancelTuning: async (operationId) => rift.cancelOperation(operationId, "Cancelled profiled tuning from dashboard"),
	listEvaluations: async (service, signal) => {
		return list((await req("GET", `/v2/evaluations${service ? `?service=${encodeURIComponent(service)}` : ""}`, void 0, signal)).evaluations).map(mapEvaluation);
	},
	getEvaluation: async (runId, signal) => mapEvaluation(await req("GET", `/v2/evaluations/${encodeURIComponent(runId)}`, void 0, signal)),
	evaluateService: async (service, options = {}) => {
		return mapEvaluation(await resolveOperation(await req("POST", "/v2/evaluations", {
			service,
			suite: options.suite,
			max_tokens: options.maxTokens ?? 128,
			deadline_seconds: options.deadlineSeconds ?? 60,
			retain_responses: options.retainResponses ?? false,
			required: options.required ?? false,
			judge: options.judge
		})));
	},
	cancelOperation: async (operationId, reason = "Cancelled from dashboard") => mapOperation(await req("POST", `/v2/operations/${encodeURIComponent(operationId)}/cancel`, { reason }), "unknown", "unknown"),
	restartService: async (service) => {
		return resolveDeploymentAction(await req("POST", `/v2/deployments/${encodeURIComponent(service)}/actions`, {
			service,
			action: "restart",
			allow_launch: true
		}), service);
	},
	recoverService: async (service) => {
		return resolveDeploymentAction(await req("POST", `/v2/deployments/${encodeURIComponent(service)}/actions`, {
			service,
			action: "recover",
			allow_launch: true
		}), service);
	},
	rollback: async (service) => {
		return resolveDeploymentAction(await req("POST", `/v2/deployments/${encodeURIComponent(service)}/actions`, {
			service,
			action: "rollback",
			allow_launch: true
		}), service);
	},
	listIncidents,
	acknowledgeIncident: async () => {
		throw new RiftUnavailable("/incidents/actions", "POST", "not-implemented");
	},
	resolveIncident: async () => {
		throw new RiftUnavailable("/incidents/actions", "POST", "not-implemented");
	},
	planYaml: async (planId) => {
		const generated = planId ? await req("GET", `/v2/plans/${encodeURIComponent(planId)}`) : await req("GET", "/generated-config");
		return JSON.stringify(generated, null, 2);
	},
	timeline: (signal) => req("GET", "/timeline", void 0, signal),
	logs: (signal, service) => req("GET", `/logs?service=${encodeURIComponent(service || "chat")}`, void 0, signal),
	backends: (signal) => req("GET", "/backends", void 0, signal),
	reports: (signal) => req("GET", "/reports", void 0, signal),
	settings: async (signal) => {
		const payload = await req("GET", "/v2/settings", void 0, signal);
		return {
			apiVersion: text(payload.api_version, "2"),
			available: bool(payload.available, true),
			configPath: text(payload.config_path) || void 0,
			configError: text(payload.config_error) || void 0,
			modelSources: object(payload.model_sources),
			gateway: object(payload.gateway),
			services: Object.fromEntries(Object.entries(object(payload.services)).map(([key, value]) => [key, object(value)])),
			policies: object(payload.policies),
			mesh: object(payload.mesh)
		};
	},
	currentPlan,
	benchmarkService: async (service, prompt = "Explain what RIFT does in one sentence.", maxTokens = 32) => resolveOperation(await req("POST", "/benchmark", {
		service,
		prompt,
		max_tokens: maxTokens
	})),
	benchmarkSuite: async (service, options = {}) => resolveOperation(await req("POST", "/benchmark-suite", {
		service,
		prompt: options.prompt,
		max_tokens: options.maxTokens ?? 48,
		warmups: options.warmups ?? 1,
		repetitions: options.repetitions ?? 3,
		concurrency: options.concurrency ?? 1
	})),
	tuneService: async (service, options = {}) => resolveOperation(await req("POST", "/tune", {
		service,
		live: options.live ?? false,
		allow_restart: options.allowRestart ?? false,
		candidate_limit: options.candidateLimit ?? 4
	})),
	destroyService: async (service) => req("POST", "/destroy", { service }),
	relaunchDeployment: async (deploymentId, options = {}) => resolveOperation(await req("POST", `/v2/deployment-records/${encodeURIComponent(deploymentId)}/launch`, {
		allow_download: options.allowDownload ?? false,
		allow_install: options.allowInstall ?? false,
		allow_launch: options.allowLaunch ?? false,
		allow_remote: options.allowRemote ?? false,
		optimize: options.optimize ?? false
	})),
	subscribe(onEvent, onStale) {
		let closed = false;
		const poll = async () => {
			try {
				const health = await fleetHealth();
				if (!closed) {
					onStale(false);
					onEvent({
						kind: "health",
						health
					});
				}
			} catch {
				if (!closed) onStale(true);
			}
		};
		poll();
		const timer = setInterval(poll, 1e4);
		return () => {
			closed = true;
			clearInterval(timer);
		};
	}
};
//#endregion
//#region src/components/rift/unavailable.tsx
var import_jsx_runtime = require_jsx_runtime();
/**
* `Unavailable` — shown wherever a required RIFT controller endpoint is
* not reachable. Per spec: never silently substitute mock data. Instead
* we name the endpoint, method, and expected resource shape so operators
* can wire it up (or confirm the controller is offline).
*/
function Unavailable({ endpoint, method = "GET", resource, hint, reason }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "rift-surface p-5",
		role: "status",
		"aria-live": "polite",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-start gap-3",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, {
				className: "size-4 mt-0.5 text-attention shrink-0",
				"aria-hidden": true
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "min-w-0",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label mb-1 text-ink",
						children: "Data unavailable"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "text-[13px] text-ink-secondary max-w-xl",
						children: reason ?? "The controller endpoint required to render this view is not reachable."
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-3 grid gap-1.5 text-[12.5px] rift-mono",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex gap-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-ink-secondary w-16",
								children: "endpoint"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "text-ink",
								children: [
									method,
									" ",
									endpoint
								]
							})]
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex gap-2",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-ink-secondary w-16",
								children: "returns"
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-ink",
								children: resource
							})]
						})]
					}),
					hint && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 text-[12px] text-ink-secondary max-w-xl",
						children: hint
					})
				]
			})]
		})
	});
}
//#endregion
export { TriangleAlert as a, cn as i, RiftUnavailable as n, Terminal as o, rift as r, createLucideIcon as s, Unavailable as t };
