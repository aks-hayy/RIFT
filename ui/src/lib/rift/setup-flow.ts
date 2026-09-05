export type SetupStepVisibility = (index: number) => boolean;

export function getNextSetupStep(
  current: number,
  isVisible: SetupStepVisibility,
  lastStep: number,
): number {
  for (let index = current + 1; index <= lastStep; index += 1) {
    if (isVisible(index)) return index;
  }
  return current;
}

export function getPreviousSetupStep(
  current: number,
  isVisible: SetupStepVisibility,
  firstStep: number,
): number {
  for (let index = current - 1; index >= firstStep; index -= 1) {
    if (isVisible(index)) return index;
  }
  return current;
}
