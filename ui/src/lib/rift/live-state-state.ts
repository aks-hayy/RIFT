export type LiveDataState = "loading" | "empty" | "unavailable" | "error" | "unsupported" | "ready";

export type LiveStateInput = {
  isLoading: boolean;
  hasData: boolean;
  unavailable?: boolean;
  error?: boolean;
  unsupported?: boolean;
  empty?: boolean;
};

export function resolveLiveState(input: LiveStateInput): LiveDataState {
  if (input.unsupported) return "unsupported";
  if (input.unavailable) return "unavailable";
  if (input.error) return "error";
  if (input.isLoading && !input.hasData) return "loading";
  if (!input.hasData || input.empty) return "empty";
  return "ready";
}
