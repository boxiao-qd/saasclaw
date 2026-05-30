export type FourState = "loading" | "empty" | "error" | "success";

export interface ComponentState<T> {
  state: FourState;
  data?: T;
  error?: string;
}