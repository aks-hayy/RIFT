import { i as require_react, r as require_jsx_runtime, s as __toESM, t as useRouter } from "./useRouter-C_cgokP9.js";
import { t as useStore } from "./useStore-YNjTxDUy.js";
import { t as Link } from "./link-DZw2_uJJ.js";
import { A as useStructuralSharing, C as shouldThrowError, D as focusManager, E as timeoutManager, O as Subscribable, S as shallowEqualObjects, T as timeUntilStale, _ as noop, b as resolveQueryBoolean, c as notifyManager, i as fetchState, l as pendingThenable, m as isValidTimeout, n as useQueryClient, u as environmentManager, x as resolveStaleTime, y as replaceData } from "./QueryClientProvider-B2PFp0e-.js";
import { c as createLucideIcon, i as cn, n as RiftUnavailable, o as Terminal, r as rift } from "./unavailable-Dh9iADmt.js";
//#region node_modules/@tanstack/react-router/dist/esm/useRouterState.js
/**
* Subscribe to the router's state store with optional selection and
* structural sharing for render optimization.
*
* Options:
* - `select`: Project the full router state to a derived slice
* - `structuralSharing`: Replace-equal semantics for stable references
* - `router`: Read state from a specific router instance instead of context
*
* @returns The selected router state (or the full state by default).
* @link https://tanstack.com/router/latest/docs/framework/react/api/router/useRouterStateHook
*/
function useRouterState(opts) {
	const contextRouter = useRouter({ warn: opts?.router === void 0 });
	const router = opts?.router || contextRouter;
	{
		const state = router.stores.__store.get();
		return opts?.select ? opts.select(state) : state;
	}
	return useStore(router.stores.__store, useStructuralSharing(opts, router));
}
//#endregion
//#region node_modules/@tanstack/query-core/build/modern/queryObserver.js
var QueryObserver = class extends Subscribable {
	constructor(client, options) {
		super();
		this.options = options;
		this.#client = client;
		this.#selectError = null;
		this.#currentThenable = pendingThenable();
		this.bindMethods();
		this.setOptions(options);
	}
	#client;
	#currentQuery = void 0;
	#currentQueryInitialState = void 0;
	#currentResult = void 0;
	#currentResultState;
	#currentResultOptions;
	#currentThenable;
	#selectError;
	#selectFn;
	#selectResult;
	#lastQueryWithDefinedData;
	#staleTimeoutId;
	#refetchIntervalId;
	#currentRefetchInterval;
	#trackedProps = /* @__PURE__ */ new Set();
	bindMethods() {
		this.refetch = this.refetch.bind(this);
	}
	onSubscribe() {
		if (this.listeners.size === 1) {
			this.#currentQuery.addObserver(this);
			if (shouldFetchOnMount(this.#currentQuery, this.options)) this.#executeFetch();
			else this.updateResult();
			this.#updateTimers();
		}
	}
	onUnsubscribe() {
		if (!this.hasListeners()) this.destroy();
	}
	shouldFetchOnReconnect() {
		return shouldFetchOn(this.#currentQuery, this.options, this.options.refetchOnReconnect);
	}
	shouldFetchOnWindowFocus() {
		return shouldFetchOn(this.#currentQuery, this.options, this.options.refetchOnWindowFocus);
	}
	destroy() {
		this.listeners = /* @__PURE__ */ new Set();
		this.#clearStaleTimeout();
		this.#clearRefetchInterval();
		this.#currentQuery.removeObserver(this);
	}
	setOptions(options) {
		const prevOptions = this.options;
		const prevQuery = this.#currentQuery;
		this.options = this.#client.defaultQueryOptions(options);
		if (this.options.enabled !== void 0 && typeof this.options.enabled !== "boolean" && typeof this.options.enabled !== "function" && typeof resolveQueryBoolean(this.options.enabled, this.#currentQuery) !== "boolean") throw new Error("Expected enabled to be a boolean or a callback that returns a boolean");
		this.#updateQuery();
		this.#currentQuery.setOptions(this.options);
		if (prevOptions._defaulted && !shallowEqualObjects(this.options, prevOptions)) this.#client.getQueryCache().notify({
			type: "observerOptionsUpdated",
			query: this.#currentQuery,
			observer: this
		});
		const mounted = this.hasListeners();
		if (mounted && shouldFetchOptionally(this.#currentQuery, prevQuery, this.options, prevOptions)) this.#executeFetch();
		this.updateResult();
		if (mounted && (this.#currentQuery !== prevQuery || resolveQueryBoolean(this.options.enabled, this.#currentQuery) !== resolveQueryBoolean(prevOptions.enabled, this.#currentQuery) || resolveStaleTime(this.options.staleTime, this.#currentQuery) !== resolveStaleTime(prevOptions.staleTime, this.#currentQuery))) this.#updateStaleTimeout();
		const nextRefetchInterval = this.#computeRefetchInterval();
		if (mounted && (this.#currentQuery !== prevQuery || resolveQueryBoolean(this.options.enabled, this.#currentQuery) !== resolveQueryBoolean(prevOptions.enabled, this.#currentQuery) || nextRefetchInterval !== this.#currentRefetchInterval)) this.#updateRefetchInterval(nextRefetchInterval);
	}
	getOptimisticResult(options) {
		const query = this.#client.getQueryCache().build(this.#client, options);
		const result = this.createResult(query, options);
		if (shouldAssignObserverCurrentProperties(this, result)) {
			this.#currentResult = result;
			this.#currentResultOptions = this.options;
			this.#currentResultState = this.#currentQuery.state;
		}
		return result;
	}
	getCurrentResult() {
		return this.#currentResult;
	}
	trackResult(result, onPropTracked) {
		return new Proxy(result, { get: (target, key) => {
			this.trackProp(key);
			onPropTracked?.(key);
			if (key === "promise") {
				this.trackProp("data");
				if (!this.options.experimental_prefetchInRender && this.#currentThenable.status === "pending") this.#currentThenable.reject(/* @__PURE__ */ new Error("experimental_prefetchInRender feature flag is not enabled"));
			}
			return Reflect.get(target, key);
		} });
	}
	trackProp(key) {
		this.#trackedProps.add(key);
	}
	getCurrentQuery() {
		return this.#currentQuery;
	}
	refetch({ ...options } = {}) {
		return this.fetch({ ...options });
	}
	fetchOptimistic(options) {
		const defaultedOptions = this.#client.defaultQueryOptions(options);
		const query = this.#client.getQueryCache().build(this.#client, defaultedOptions);
		return query.fetch().then(() => this.createResult(query, defaultedOptions));
	}
	fetch(fetchOptions) {
		return this.#executeFetch({
			...fetchOptions,
			cancelRefetch: fetchOptions.cancelRefetch ?? true
		}).then(() => {
			this.updateResult();
			return this.#currentResult;
		});
	}
	#executeFetch(fetchOptions) {
		this.#updateQuery();
		let promise = this.#currentQuery.fetch(this.options, fetchOptions);
		if (!fetchOptions?.throwOnError) promise = promise.catch(noop);
		return promise;
	}
	#updateStaleTimeout() {
		this.#clearStaleTimeout();
		const staleTime = resolveStaleTime(this.options.staleTime, this.#currentQuery);
		if (environmentManager.isServer() || this.#currentResult.isStale || !isValidTimeout(staleTime)) return;
		const timeout = timeUntilStale(this.#currentResult.dataUpdatedAt, staleTime) + 1;
		this.#staleTimeoutId = timeoutManager.setTimeout(() => {
			if (!this.#currentResult.isStale) this.updateResult();
		}, timeout);
	}
	#computeRefetchInterval() {
		return (typeof this.options.refetchInterval === "function" ? this.options.refetchInterval(this.#currentQuery) : this.options.refetchInterval) ?? false;
	}
	#updateRefetchInterval(nextInterval) {
		this.#clearRefetchInterval();
		this.#currentRefetchInterval = nextInterval;
		if (environmentManager.isServer() || resolveQueryBoolean(this.options.enabled, this.#currentQuery) === false || !isValidTimeout(this.#currentRefetchInterval) || this.#currentRefetchInterval === 0) return;
		this.#refetchIntervalId = timeoutManager.setInterval(() => {
			if (this.options.refetchIntervalInBackground || focusManager.isFocused()) this.#executeFetch();
		}, this.#currentRefetchInterval);
	}
	#updateTimers() {
		this.#updateStaleTimeout();
		this.#updateRefetchInterval(this.#computeRefetchInterval());
	}
	#clearStaleTimeout() {
		if (this.#staleTimeoutId !== void 0) {
			timeoutManager.clearTimeout(this.#staleTimeoutId);
			this.#staleTimeoutId = void 0;
		}
	}
	#clearRefetchInterval() {
		if (this.#refetchIntervalId !== void 0) {
			timeoutManager.clearInterval(this.#refetchIntervalId);
			this.#refetchIntervalId = void 0;
		}
	}
	createResult(query, options) {
		const prevQuery = this.#currentQuery;
		const prevOptions = this.options;
		const prevResult = this.#currentResult;
		const prevResultState = this.#currentResultState;
		const prevResultOptions = this.#currentResultOptions;
		const queryInitialState = query !== prevQuery ? query.state : this.#currentQueryInitialState;
		const { state } = query;
		let newState = { ...state };
		let isPlaceholderData = false;
		let data;
		if (options._optimisticResults) {
			const mounted = this.hasListeners();
			const fetchOnMount = !mounted && shouldFetchOnMount(query, options);
			const fetchOptionally = mounted && shouldFetchOptionally(query, prevQuery, options, prevOptions);
			if (fetchOnMount || fetchOptionally) newState = {
				...newState,
				...fetchState(state.data, query.options)
			};
			if (options._optimisticResults === "isRestoring") newState.fetchStatus = "idle";
		}
		let { error, errorUpdatedAt, status } = newState;
		data = newState.data;
		let skipSelect = false;
		if (options.placeholderData !== void 0 && data === void 0 && status === "pending") {
			let placeholderData;
			if (prevResult?.isPlaceholderData && options.placeholderData === prevResultOptions?.placeholderData) {
				placeholderData = prevResult.data;
				skipSelect = true;
			} else placeholderData = typeof options.placeholderData === "function" ? options.placeholderData(this.#lastQueryWithDefinedData?.state.data, this.#lastQueryWithDefinedData) : options.placeholderData;
			if (placeholderData !== void 0) {
				status = "success";
				data = replaceData(prevResult?.data, placeholderData, options);
				isPlaceholderData = true;
			}
		}
		if (options.select && data !== void 0 && !skipSelect) if (prevResult && data === prevResultState?.data && options.select === this.#selectFn) data = this.#selectResult;
		else try {
			this.#selectFn = options.select;
			data = options.select(data);
			data = replaceData(prevResult?.data, data, options);
			this.#selectResult = data;
			this.#selectError = null;
		} catch (selectError) {
			this.#selectError = selectError;
		}
		if (this.#selectError) {
			error = this.#selectError;
			data = this.#selectResult;
			errorUpdatedAt = Date.now();
			status = "error";
		}
		const isFetching = newState.fetchStatus === "fetching";
		const isPending = status === "pending";
		const isError = status === "error";
		const isLoading = isPending && isFetching;
		const hasData = data !== void 0;
		const nextResult = {
			status,
			fetchStatus: newState.fetchStatus,
			isPending,
			isSuccess: status === "success",
			isError,
			isInitialLoading: isLoading,
			isLoading,
			data,
			dataUpdatedAt: newState.dataUpdatedAt,
			error,
			errorUpdatedAt,
			failureCount: newState.fetchFailureCount,
			failureReason: newState.fetchFailureReason,
			errorUpdateCount: newState.errorUpdateCount,
			isFetched: query.isFetched(),
			isFetchedAfterMount: newState.dataUpdateCount > queryInitialState.dataUpdateCount || newState.errorUpdateCount > queryInitialState.errorUpdateCount,
			isFetching,
			isRefetching: isFetching && !isPending,
			isLoadingError: isError && !hasData,
			isPaused: newState.fetchStatus === "paused",
			isPlaceholderData,
			isRefetchError: isError && hasData,
			isStale: isStale(query, options),
			refetch: this.refetch,
			promise: this.#currentThenable,
			isEnabled: resolveQueryBoolean(options.enabled, query) !== false
		};
		if (this.options.experimental_prefetchInRender) {
			const hasResultData = nextResult.data !== void 0;
			const isErrorWithoutData = nextResult.status === "error" && !hasResultData;
			const finalizeThenableIfPossible = (thenable) => {
				if (isErrorWithoutData) thenable.reject(nextResult.error);
				else if (hasResultData) thenable.resolve(nextResult.data);
			};
			const recreateThenable = () => {
				const pending = this.#currentThenable = nextResult.promise = pendingThenable();
				finalizeThenableIfPossible(pending);
			};
			const prevThenable = this.#currentThenable;
			switch (prevThenable.status) {
				case "pending":
					if (query.queryHash === prevQuery.queryHash) finalizeThenableIfPossible(prevThenable);
					break;
				case "fulfilled":
					if (isErrorWithoutData || nextResult.data !== prevThenable.value) recreateThenable();
					break;
				case "rejected":
					if (!isErrorWithoutData || nextResult.error !== prevThenable.reason) recreateThenable();
					break;
			}
		}
		return nextResult;
	}
	updateResult() {
		const prevResult = this.#currentResult;
		const nextResult = this.createResult(this.#currentQuery, this.options);
		this.#currentResultState = this.#currentQuery.state;
		this.#currentResultOptions = this.options;
		if (this.#currentResultState.data !== void 0) this.#lastQueryWithDefinedData = this.#currentQuery;
		if (shallowEqualObjects(nextResult, prevResult)) return;
		this.#currentResult = nextResult;
		const shouldNotifyListeners = () => {
			if (!prevResult) return true;
			const { notifyOnChangeProps } = this.options;
			const notifyOnChangePropsValue = typeof notifyOnChangeProps === "function" ? notifyOnChangeProps() : notifyOnChangeProps;
			if (notifyOnChangePropsValue === "all" || !notifyOnChangePropsValue && !this.#trackedProps.size) return true;
			const includedProps = new Set(notifyOnChangePropsValue ?? this.#trackedProps);
			if (this.options.throwOnError) includedProps.add("error");
			return Object.keys(this.#currentResult).some((key) => {
				const typedKey = key;
				return this.#currentResult[typedKey] !== prevResult[typedKey] && includedProps.has(typedKey);
			});
		};
		this.#notify({ listeners: shouldNotifyListeners() });
	}
	#updateQuery() {
		const query = this.#client.getQueryCache().build(this.#client, this.options);
		if (query === this.#currentQuery) return;
		const prevQuery = this.#currentQuery;
		this.#currentQuery = query;
		this.#currentQueryInitialState = query.state;
		if (this.hasListeners()) {
			prevQuery?.removeObserver(this);
			query.addObserver(this);
		}
	}
	onQueryUpdate() {
		this.updateResult();
		if (this.hasListeners()) this.#updateTimers();
	}
	#notify(notifyOptions) {
		notifyManager.batch(() => {
			if (notifyOptions.listeners) this.listeners.forEach((listener) => {
				listener(this.#currentResult);
			});
			this.#client.getQueryCache().notify({
				query: this.#currentQuery,
				type: "observerResultsUpdated"
			});
		});
	}
};
function shouldLoadOnMount(query, options) {
	return resolveQueryBoolean(options.enabled, query) !== false && query.state.data === void 0 && !(query.state.status === "error" && resolveQueryBoolean(options.retryOnMount, query) === false);
}
function shouldFetchOnMount(query, options) {
	return shouldLoadOnMount(query, options) || query.state.data !== void 0 && shouldFetchOn(query, options, options.refetchOnMount);
}
function shouldFetchOn(query, options, field) {
	if (resolveQueryBoolean(options.enabled, query) !== false && resolveStaleTime(options.staleTime, query) !== "static") {
		const value = typeof field === "function" ? field(query) : field;
		return value === "always" || value !== false && isStale(query, options);
	}
	return false;
}
function shouldFetchOptionally(query, prevQuery, options, prevOptions) {
	return (query !== prevQuery || resolveQueryBoolean(prevOptions.enabled, query) === false) && (!options.suspense || query.state.status !== "error") && isStale(query, options);
}
function isStale(query, options) {
	return resolveQueryBoolean(options.enabled, query) !== false && query.isStaleByTime(resolveStaleTime(options.staleTime, query));
}
function shouldAssignObserverCurrentProperties(observer, optimisticResult) {
	if (!shallowEqualObjects(observer.getCurrentResult(), optimisticResult)) return true;
	return false;
}
//#endregion
//#region node_modules/@tanstack/react-query/build/modern/IsRestoringProvider.js
var import_jsx_runtime = require_jsx_runtime();
var import_react = /* @__PURE__ */ __toESM(require_react(), 1);
var IsRestoringContext = import_react.createContext(false);
var useIsRestoring = () => import_react.useContext(IsRestoringContext);
IsRestoringContext.Provider;
//#endregion
//#region node_modules/@tanstack/react-query/build/modern/QueryErrorResetBoundary.js
function createValue() {
	let isReset = false;
	return {
		clearReset: () => {
			isReset = false;
		},
		reset: () => {
			isReset = true;
		},
		isReset: () => {
			return isReset;
		}
	};
}
var QueryErrorResetBoundaryContext = import_react.createContext(createValue());
var useQueryErrorResetBoundary = () => import_react.useContext(QueryErrorResetBoundaryContext);
//#endregion
//#region node_modules/@tanstack/react-query/build/modern/errorBoundaryUtils.js
var ensurePreventErrorBoundaryRetry = (options, errorResetBoundary, query) => {
	const throwOnError = query?.state.error && typeof options.throwOnError === "function" ? shouldThrowError(options.throwOnError, [query.state.error, query]) : options.throwOnError;
	if (options.suspense || options.experimental_prefetchInRender || throwOnError) {
		if (!errorResetBoundary.isReset()) options.retryOnMount = false;
	}
};
var useClearResetErrorBoundary = (errorResetBoundary) => {
	import_react.useEffect(() => {
		errorResetBoundary.clearReset();
	}, [errorResetBoundary]);
};
var getHasError = ({ result, errorResetBoundary, throwOnError, query, suspense }) => {
	return result.isError && !errorResetBoundary.isReset() && !result.isFetching && query && (suspense && result.data === void 0 || shouldThrowError(throwOnError, [result.error, query]));
};
//#endregion
//#region node_modules/@tanstack/react-query/build/modern/suspense.js
var ensureSuspenseTimers = (defaultedOptions) => {
	if (defaultedOptions.suspense) {
		const MIN_SUSPENSE_TIME_MS = 1e3;
		const clamp = (value) => value === "static" ? value : Math.max(value ?? MIN_SUSPENSE_TIME_MS, MIN_SUSPENSE_TIME_MS);
		const originalStaleTime = defaultedOptions.staleTime;
		defaultedOptions.staleTime = typeof originalStaleTime === "function" ? (...args) => clamp(originalStaleTime(...args)) : clamp(originalStaleTime);
		if (typeof defaultedOptions.gcTime === "number") defaultedOptions.gcTime = Math.max(defaultedOptions.gcTime, MIN_SUSPENSE_TIME_MS);
	}
};
var willFetch = (result, isRestoring) => result.isLoading && result.isFetching && !isRestoring;
var shouldSuspend = (defaultedOptions, result) => defaultedOptions?.suspense && result.isPending;
var fetchOptimistic = (defaultedOptions, observer, errorResetBoundary) => observer.fetchOptimistic(defaultedOptions).catch(() => {
	errorResetBoundary.clearReset();
});
//#endregion
//#region node_modules/@tanstack/react-query/build/modern/useBaseQuery.js
function useBaseQuery(options, Observer, queryClient) {
	const isRestoring = useIsRestoring();
	const errorResetBoundary = useQueryErrorResetBoundary();
	const client = useQueryClient(queryClient);
	const defaultedOptions = client.defaultQueryOptions(options);
	client.getDefaultOptions().queries?._experimental_beforeQuery?.(defaultedOptions);
	const query = client.getQueryCache().get(defaultedOptions.queryHash);
	const subscribed = options.subscribed !== false;
	defaultedOptions._optimisticResults = isRestoring ? "isRestoring" : subscribed ? "optimistic" : void 0;
	ensureSuspenseTimers(defaultedOptions);
	ensurePreventErrorBoundaryRetry(defaultedOptions, errorResetBoundary, query);
	useClearResetErrorBoundary(errorResetBoundary);
	const isNewCacheEntry = !client.getQueryCache().get(defaultedOptions.queryHash);
	const [observer] = import_react.useState(() => new Observer(client, defaultedOptions));
	const result = observer.getOptimisticResult(defaultedOptions);
	const shouldSubscribe = !isRestoring && subscribed;
	import_react.useSyncExternalStore(import_react.useCallback((onStoreChange) => {
		const unsubscribe = shouldSubscribe ? observer.subscribe(notifyManager.batchCalls(onStoreChange)) : noop;
		observer.updateResult();
		return unsubscribe;
	}, [observer, shouldSubscribe]), () => observer.getCurrentResult(), () => observer.getCurrentResult());
	import_react.useEffect(() => {
		observer.setOptions(defaultedOptions);
	}, [defaultedOptions, observer]);
	if (shouldSuspend(defaultedOptions, result)) throw fetchOptimistic(defaultedOptions, observer, errorResetBoundary);
	if (getHasError({
		result,
		errorResetBoundary,
		throwOnError: defaultedOptions.throwOnError,
		query,
		suspense: defaultedOptions.suspense
	})) throw result.error;
	client.getDefaultOptions().queries?._experimental_afterQuery?.(defaultedOptions, result);
	if (defaultedOptions.experimental_prefetchInRender && !environmentManager.isServer() && willFetch(result, isRestoring)) (isNewCacheEntry ? fetchOptimistic(defaultedOptions, observer, errorResetBoundary) : query?.promise)?.catch(noop).finally(() => {
		observer.updateResult();
	});
	return !defaultedOptions.notifyOnChangeProps ? observer.trackResult(result) : result;
}
//#endregion
//#region node_modules/@tanstack/react-query/build/modern/useQuery.js
function useQuery(options, queryClient) {
	return useBaseQuery(options, QueryObserver, queryClient);
}
//#endregion
//#region node_modules/@tanstack/react-query/build/modern/queryOptions.js
function queryOptions(options) {
	return options;
}
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Activity = createLucideIcon("activity", [["path", {
	d: "M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2",
	key: "169zse"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Boxes = createLucideIcon("boxes", [
	["path", {
		d: "M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z",
		key: "lc1i9w"
	}],
	["path", {
		d: "m7 16.5-4.74-2.85",
		key: "1o9zyk"
	}],
	["path", {
		d: "m7 16.5 5-3",
		key: "va8pkn"
	}],
	["path", {
		d: "M7 16.5v5.17",
		key: "jnp8gn"
	}],
	["path", {
		d: "M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z",
		key: "8zsnat"
	}],
	["path", {
		d: "m17 16.5-5-3",
		key: "8arw3v"
	}],
	["path", {
		d: "m17 16.5 4.74-2.85",
		key: "8rfmw"
	}],
	["path", {
		d: "M17 16.5v5.17",
		key: "k6z78m"
	}],
	["path", {
		d: "M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z",
		key: "1xygjf"
	}],
	["path", {
		d: "M12 8 7.26 5.15",
		key: "1vbdud"
	}],
	["path", {
		d: "m12 8 4.74-2.85",
		key: "3rx089"
	}],
	["path", {
		d: "M12 13.5V8",
		key: "1io7kd"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var CircleDot = createLucideIcon("circle-dot", [["circle", {
	cx: "12",
	cy: "12",
	r: "10",
	key: "1mglay"
}], ["circle", {
	cx: "12",
	cy: "12",
	r: "1",
	key: "41hilf"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var House = createLucideIcon("house", [["path", {
	d: "M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8",
	key: "5wwlr5"
}], ["path", {
	d: "M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
	key: "r6nss1"
}]]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Menu = createLucideIcon("menu", [
	["path", {
		d: "M4 5h16",
		key: "1tepv9"
	}],
	["path", {
		d: "M4 12h16",
		key: "1lakjw"
	}],
	["path", {
		d: "M4 19h16",
		key: "1djgab"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Package = createLucideIcon("package", [
	["path", {
		d: "M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z",
		key: "1a0edw"
	}],
	["path", {
		d: "M12 22V12",
		key: "d0xqtd"
	}],
	["polyline", {
		points: "3.29 7 12 12 20.71 7",
		key: "ousv84"
	}],
	["path", {
		d: "m7.5 4.27 9 5.15",
		key: "1c824w"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Server = createLucideIcon("server", [
	["rect", {
		width: "20",
		height: "8",
		x: "2",
		y: "2",
		rx: "2",
		ry: "2",
		key: "ngkwjq"
	}],
	["rect", {
		width: "20",
		height: "8",
		x: "2",
		y: "14",
		rx: "2",
		ry: "2",
		key: "iecqi9"
	}],
	["line", {
		x1: "6",
		x2: "6.01",
		y1: "6",
		y2: "6",
		key: "16zg32"
	}],
	["line", {
		x1: "6",
		x2: "6.01",
		y1: "18",
		y2: "18",
		key: "nzw8ys"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Settings2 = createLucideIcon("settings-2", [
	["path", {
		d: "M14 17H5",
		key: "gfn3mx"
	}],
	["path", {
		d: "M19 7h-9",
		key: "6i9tg"
	}],
	["circle", {
		cx: "17",
		cy: "17",
		r: "3",
		key: "18b49y"
	}],
	["circle", {
		cx: "7",
		cy: "7",
		r: "3",
		key: "dfmy0x"
	}]
]);
/**
* @license lucide-react v0.575.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var X = createLucideIcon("x", [["path", {
	d: "M18 6 6 18",
	key: "1bl5f8"
}], ["path", {
	d: "m6 6 12 12",
	key: "d8bk6v"
}]]);
//#endregion
//#region src/lib/rift/hooks.ts
var keys = {
	health: ["rift", "health"],
	nodes: ["rift", "nodes"],
	node: (id) => [
		"rift",
		"node",
		id
	],
	meshSightings: [
		"rift",
		"mesh",
		"sightings"
	],
	meshNodes: [
		"rift",
		"mesh",
		"nodes"
	],
	meshTopology: [
		"rift",
		"mesh",
		"topology"
	],
	services: ["rift", "services"],
	service: (id) => [
		"rift",
		"service",
		id
	],
	revisions: (id) => [
		"rift",
		"revisions",
		id
	],
	benchmarks: (id) => [
		"rift",
		"benchmarks",
		id
	],
	incidents: ["rift", "incidents"],
	timeline: ["rift", "timeline"],
	logs: ["rift", "logs"],
	backends: ["rift", "backends"],
	reports: ["rift", "reports"],
	latestPlan: ["rift", "latest-plan"],
	plan: (id) => [
		"rift",
		"plan",
		id
	]
};
function shape(q) {
	const err = q.error;
	return {
		data: q.data,
		isLoading: q.isPending,
		unavailable: err instanceof RiftUnavailable ? err : null,
		error: err instanceof RiftUnavailable ? null : err ?? null,
		refetch: () => void q.refetch()
	};
}
var healthOptions = queryOptions({
	queryKey: keys.health,
	queryFn: ({ signal }) => rift.health(signal),
	staleTime: 5e3,
	refetchInterval: 15e3,
	retry: false
});
var nodesOptions = queryOptions({
	queryKey: keys.nodes,
	queryFn: ({ signal }) => rift.listNodes(signal),
	staleTime: 5e3,
	refetchInterval: 15e3,
	retry: false
});
var servicesOptions = queryOptions({
	queryKey: keys.services,
	queryFn: ({ signal }) => rift.listServices(signal),
	staleTime: 5e3,
	refetchInterval: 2e4,
	retry: false
});
var incidentsOptions = queryOptions({
	queryKey: keys.incidents,
	queryFn: ({ signal }) => rift.listIncidents(signal),
	staleTime: 5e3,
	refetchInterval: 15e3,
	retry: false
});
function useHealth() {
	return shape(useQuery(healthOptions));
}
function useNodes() {
	return shape(useQuery(nodesOptions));
}
function useMeshNodes() {
	return shape(useQuery({
		queryKey: keys.meshNodes,
		queryFn: ({ signal }) => rift.listMeshNodes(signal),
		staleTime: 3e3,
		refetchInterval: 1e4,
		retry: false
	}));
}
function useMeshTopology() {
	return shape(useQuery({
		queryKey: keys.meshTopology,
		queryFn: ({ signal }) => rift.getMeshTopology(signal),
		staleTime: 5e3,
		refetchInterval: 15e3,
		retry: false
	}));
}
function useServices() {
	return shape(useQuery(servicesOptions));
}
function useIncidents() {
	return shape(useQuery(incidentsOptions));
}
function useTimeline() {
	return shape(useQuery({
		queryKey: keys.timeline,
		queryFn: ({ signal }) => rift.timeline(signal),
		staleTime: 5e3,
		refetchInterval: 15e3,
		retry: false
	}));
}
function useLogs() {
	return shape(useQuery({
		queryKey: keys.logs,
		queryFn: ({ signal }) => rift.logs(signal),
		staleTime: 3e3,
		refetchInterval: 1e4,
		retry: false
	}));
}
function useBackends() {
	return shape(useQuery({
		queryKey: keys.backends,
		queryFn: ({ signal }) => rift.backends(signal),
		staleTime: 15e3,
		refetchInterval: 3e4,
		retry: false
	}));
}
function useReports() {
	return shape(useQuery({
		queryKey: keys.reports,
		queryFn: ({ signal }) => rift.reports(signal),
		staleTime: 15e3,
		retry: false
	}));
}
function useLatestPlan() {
	return shape(useQuery({
		queryKey: keys.latestPlan,
		queryFn: ({ signal }) => rift.currentPlan(signal),
		staleTime: 15e3,
		retry: false
	}));
}
function useNode(id) {
	return shape(useQuery({
		queryKey: id ? keys.node(id) : [
			"rift",
			"node",
			"none"
		],
		queryFn: ({ signal }) => rift.getNode(id, signal),
		enabled: !!id,
		retry: false
	}));
}
function useService(id) {
	return shape(useQuery({
		queryKey: id ? keys.service(id) : [
			"rift",
			"service",
			"none"
		],
		queryFn: ({ signal }) => rift.getService(id, signal),
		enabled: !!id,
		retry: false
	}));
}
function useRevisions(serviceId) {
	return shape(useQuery({
		queryKey: serviceId ? keys.revisions(serviceId) : [
			"rift",
			"revisions",
			"none"
		],
		queryFn: ({ signal }) => rift.listRevisions(serviceId, signal),
		enabled: !!serviceId,
		retry: false
	}));
}
function useBenchmarks(serviceId) {
	return shape(useQuery({
		queryKey: serviceId ? keys.benchmarks(serviceId) : [
			"rift",
			"benchmarks",
			"none"
		],
		queryFn: ({ signal }) => rift.listBenchmarks(serviceId, signal),
		enabled: !!serviceId,
		retry: false
	}));
}
function recommendationKey(input) {
	return [
		"rift",
		"recommend",
		input
	];
}
function useRecommendations(input) {
	return shape(useQuery({
		queryKey: input ? recommendationKey(input) : [
			"rift",
			"recommend",
			"none"
		],
		queryFn: () => rift.recommend(input),
		enabled: !!input,
		retry: false,
		staleTime: 6e4
	}));
}
//#endregion
//#region src/components/rift/app-shell.tsx
var NAV = [
	{
		to: "/",
		label: "Home",
		icon: House,
		exact: true
	},
	{
		to: "/deployments",
		label: "Deployments",
		icon: Boxes
	},
	{
		to: "/nodes",
		label: "Nodes",
		icon: Server
	},
	{
		to: "/models",
		label: "Models",
		icon: Package
	},
	{
		to: "/operations",
		label: "Operations",
		icon: Activity
	},
	{
		to: "/settings",
		label: "Settings",
		icon: Settings2
	}
];
function AppShell({ children }) {
	const pathname = useRouterState({ select: (s) => s.location.pathname });
	const [stale, setStale] = (0, import_react.useState)(null);
	const [mobileOpen, setMobileOpen] = (0, import_react.useState)(false);
	const qc = useQueryClient();
	const connection = rift.connectionInfo();
	(0, import_react.useEffect)(() => {
		if (!rift.isConfigured()) {
			setStale(true);
			return;
		}
		return rift.subscribe((e) => {
			switch (e.kind) {
				case "health":
					qc.setQueryData(keys.health, e.health);
					break;
				case "node.enrolled":
				case "node.status":
					qc.invalidateQueries({ queryKey: keys.nodes });
					break;
				case "service.status":
					qc.invalidateQueries({ queryKey: keys.services });
					break;
				case "incident.opened":
				case "incident.resolved":
					qc.invalidateQueries({ queryKey: keys.incidents });
					break;
				case "plan.progress": break;
			}
		}, setStale);
	}, [qc]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "min-h-dvh flex flex-col bg-canvas",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("header", {
				className: "border-b border-border bg-raised",
				role: "banner",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "max-w-[1400px] mx-auto flex items-center gap-6 px-4 h-14",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
							to: "/",
							className: "flex items-center gap-2 font-mono text-[13px] tracking-[0.14em] font-medium text-ink",
							"aria-label": "RIFT home",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RiftMark, {}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "RIFT" }),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-ink-secondary font-normal",
									children: "controller"
								})
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", {
							className: "hidden md:flex items-center gap-0.5 ml-4",
							"aria-label": "Primary",
							children: NAV.map((item) => {
								const Icon = item.icon;
								const active = item.exact ? pathname === item.to : pathname === item.to || pathname.startsWith(item.to + "/");
								return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
									to: item.to,
									className: cn("px-3 h-9 inline-flex items-center gap-2 text-[13px] rounded-[4px] transition-colors", active ? "bg-muted text-ink font-medium" : "text-ink-secondary hover:text-ink hover:bg-muted"),
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
										className: "size-3.5",
										"aria-hidden": true
									}), item.label]
								}, item.to);
							})
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "ml-auto flex items-center gap-3 text-[12px] rift-mono",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ControllerStatus, { stale }),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
									type: "button",
									className: "hidden lg:inline-flex items-center gap-1.5 text-ink-secondary hover:text-ink",
									"aria-label": "Open CLI reference",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Terminal, {
										className: "size-3.5",
										"aria-hidden": true
									}), " CLI"]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
									type: "button",
									className: "md:hidden inline-flex size-9 items-center justify-center rounded-[4px] border border-border text-ink-secondary hover:bg-muted hover:text-ink",
									"aria-label": mobileOpen ? "Close navigation" : "Open navigation",
									"aria-expanded": mobileOpen,
									onClick: () => setMobileOpen((open) => !open),
									children: mobileOpen ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(X, { className: "size-4" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Menu, { className: "size-4" })
								})
							]
						})
					]
				}), mobileOpen && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", {
					className: "md:hidden border-t border-border px-3 py-2 grid grid-cols-2 gap-1",
					"aria-label": "Mobile primary",
					children: NAV.map((item) => {
						const Icon = item.icon;
						const active = item.exact ? pathname === item.to : pathname === item.to || pathname.startsWith(item.to + "/");
						return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Link, {
							to: item.to,
							onClick: () => setMobileOpen(false),
							className: cn("h-9 px-3 inline-flex items-center gap-2 rounded-[4px] text-[13px]", active ? "bg-muted text-ink font-medium" : "text-ink-secondary hover:bg-muted"),
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
								className: "size-3.5",
								"aria-hidden": true
							}), item.label]
						}, item.to);
					})
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "border-b border-border bg-surface",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "max-w-[1400px] mx-auto min-h-7 px-4 py-1 flex flex-wrap items-center gap-x-3 gap-y-1 rift-mono text-[10.5px] text-ink-secondary",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "inline-flex items-center gap-1.5 text-secondary",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "rift-dot !size-1.5",
								"aria-hidden": true
							}), "live controller data"]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: connection.root }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "hidden sm:inline",
							children: "compatibility adapter"
						}),
						connection.previewEnabled && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "ml-auto text-attention",
							children: "preview-only surfaces are explicitly labeled"
						})
					]
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("main", {
				className: "flex-1",
				role: "main",
				children
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("footer", {
				className: "border-t border-border bg-raised",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "max-w-[1400px] mx-auto px-4 h-9 flex items-center justify-between text-[11px] rift-mono text-ink-secondary",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "RIFT · seismic operator console" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "Controller binds locally by default" })]
				})
			})
		]
	});
}
function ControllerStatus({ stale }) {
	const state = stale === null ? "connecting" : stale ? "offline" : "live";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
		className: cn("inline-flex items-center gap-1.5", stale === true ? "text-attention" : stale === null ? "text-ink-secondary" : "text-secondary"),
		title: stale === null ? "Connecting to the controller" : stale ? "Controller poll failed; retrying" : "Live controller polling",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleDot, {
			className: "size-3.5",
			"aria-hidden": true
		}), state]
	});
}
function RiftMark() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("svg", {
		width: "20",
		height: "20",
		viewBox: "0 0 20 20",
		"aria-hidden": true,
		className: "text-primary",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("path", {
			d: "M1 10 L4 10 L5.5 5 L7 15 L8.5 7 L10 13 L11.5 6 L13 14 L14.5 9 L16 11 L19 10",
			fill: "none",
			stroke: "currentColor",
			strokeWidth: "1.25",
			strokeLinecap: "square",
			strokeLinejoin: "miter"
		})
	});
}
//#endregion
//#region src/components/rift/primitives.tsx
function PageHeader({ eyebrow, title, description, actions }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "border-b border-border bg-surface",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "max-w-[1400px] mx-auto px-4 py-6 flex flex-wrap items-end justify-between gap-4",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "min-w-0",
				children: [
					eyebrow && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rift-label mb-2",
						children: eyebrow
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
						className: "text-[22px] leading-tight font-medium text-ink",
						children: title
					}),
					description && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-1.5 text-[13px] text-ink-secondary max-w-2xl",
						children: description
					})
				]
			}), actions && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "flex items-center gap-2",
				children: actions
			})]
		})
	});
}
function Panel({ title, aside, className, bodyClassName, children }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: cn("rift-panel", className),
		children: [title && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("header", {
			className: "flex items-center justify-between px-4 h-10 border-b border-border",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "rift-label",
				children: title
			}), aside]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: cn("p-4", bodyClassName),
			children
		})]
	});
}
function StatDot({ tone }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: cn("rift-dot", tone === "ok" ? "text-success" : tone === "attention" ? "text-attention" : tone === "error" ? "text-error" : tone === "info" ? "text-secondary" : "text-ink-muted"),
		"aria-hidden": true
	});
}
function KV({ label, value, mono = true }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "flex flex-col gap-1",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "rift-label",
			children: label
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: cn("text-[13px] text-ink", mono && "rift-mono"),
			children: value
		})]
	});
}
function SourceBadge({ source }) {
	if (!source) return null;
	const label = source === "derived-live" ? "live / normalized" : source;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: cn("inline-flex h-5 items-center rounded-[3px] border px-1.5 rift-mono text-[10px] uppercase", source === "preview" ? "border-attention/50 bg-attention/10 text-ink" : "border-secondary/40 bg-secondary/10 text-secondary"),
		children: label
	});
}
//#endregion
export { Activity as C, useTimeline as S, useRecommendations as _, StatDot as a, useService as b, useBenchmarks as c, useLatestPlan as d, useLogs as f, useNodes as g, useNode as h, SourceBadge as i, useHealth as l, useMeshTopology as m, PageHeader as n, AppShell as o, useMeshNodes as p, Panel as r, useBackends as s, KV as t, useIncidents as u, useReports as v, useServices as x, useRevisions as y };
