import { Alert, Loader, Center } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

/** Render loading / error states, then children with the data. */
export function Query<T>({ q, children }: { q: UseQueryResult<T, Error>; children: (d: T) => ReactNode }) {
  if (q.isLoading) return <Center p="xl"><Loader /></Center>;
  if (q.error) return <Alert color="red" title="Could not load">{q.error.message}</Alert>;
  return <>{q.data ? children(q.data) : null}</>;
}

export function toastError(e: unknown) {
  notifications.show({ color: "red", title: "Error", message: e instanceof Error ? e.message : String(e) });
}

export function toastOk(message: string) {
  notifications.show({ color: "green", message });
}
